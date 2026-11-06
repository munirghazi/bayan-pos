"""Release 2b — platform console authentication.

* Platform admins are NOT tenant users (own table, own login, own cookie).
* Login = password, then a 6-digit TOTP code (RFC 6238, 30 s, SHA-1 — what
  Google Authenticator / Microsoft Authenticator / Authy expect).
* Session = short JWT in an httpOnly cookie, signed with a key DERIVED from the
  secret (so a tenant token can never be replayed here and vice versa), sliding
  idle timeout + absolute cap.
* State-changing requests must carry `X-Platform-Request: 1`: the console and
  the tenant app share the registrable domain (same-site), so SameSite alone is
  not CSRF protection; a custom header forces a CORS pre-flight, which this
  process never approves.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import PlatformAdmin, PlatformAuditLog, SessionLocal, engine
from tenancy import get_secret_key

TOTP_STEP = 30
TOTP_DIGITS = 6
SCOPE_SESSION = "platform"
SCOPE_MFA = "platform_mfa"
MFA_TOKEN_MINUTES = 5


# ----------------------------------------------------------------- keys

def _master() -> bytes:
    return (settings.platform_secret_key or get_secret_key()).encode()


def _derive(label: str) -> bytes:
    return hmac.new(_master(), label.encode(), hashlib.sha256).digest()


def _jwt_key() -> str:
    return base64.urlsafe_b64encode(_derive("platform-session-v1")).decode()


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive("platform-totp-v1")))


def encrypt_secret(raw: str) -> str:
    return _fernet().encrypt(raw.encode()).decode()


def decrypt_secret(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# ----------------------------------------------------------------- TOTP (RFC 6238)

def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return str(code).zfill(TOTP_DIGITS)


def totp_now(secret_b32: str, at: float | None = None) -> str:
    return _hotp(secret_b32, int((at or time.time()) // TOTP_STEP))


def verify_totp(secret_b32: str, code: str, last_step: int | None, at: float | None = None) -> int | None:
    """Return the matched time-step (±1 step of clock drift), or None.
    A step at or before `last_step` is refused, so a code cannot be reused."""
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == TOTP_DIGITS):
        return None
    now = int((at or time.time()) // TOTP_STEP)
    for step in (now - 1, now, now + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_hotp(secret_b32, step), code):
            return step
    return None


def otpauth_uri(secret_b32: str, username: str) -> str:
    issuer = settings.platform_issuer
    return (f"otpauth://totp/{quote(issuer)}:{quote(username)}"
            f"?secret={secret_b32}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")


# ----------------------------------------------------------------- tokens

def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_mfa_token(admin_id: int) -> str:
    return jwt.encode({"scope": SCOPE_MFA, "aid": admin_id,
                       "exp": _now() + timedelta(minutes=MFA_TOKEN_MINUTES)},
                      _jwt_key(), algorithm="HS256")


def make_session_token(admin_id: int, started: int | None = None) -> str:
    started = started or int(time.time() * 1000)          # milliseconds
    return jwt.encode({"scope": SCOPE_SESSION, "aid": admin_id, "st": started,
                       "exp": _now() + timedelta(minutes=settings.platform_session_minutes)},
                      _jwt_key(), algorithm="HS256")


def decode(token: str, scope: str) -> dict | None:
    try:
        p = jwt.decode(token, _jwt_key(), algorithms=["HS256"])
    except JWTError:
        return None
    return p if p.get("scope") == scope else None


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(settings.platform_cookie_name, token, httponly=True,
                        secure=settings.cookie_secure, samesite="strict",
                        max_age=settings.platform_session_minutes * 60, path="/")


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(settings.platform_cookie_name, path="/")


# ----------------------------------------------------------------- DB + audit

def get_platform_db():
    """One dedicated connection per request; tenant GUC starts EMPTY (RLS shows
    no tenant rows) and is reset afterwards, whatever a handler pinned."""
    connection = engine.connect()
    connection.execute(text("SELECT set_config('app.current_tenant', '', false)"))
    connection.commit()
    db = SessionLocal(bind=connection)
    try:
        yield db
    finally:
        db.close()
        try:
            connection.execute(text("SELECT set_config('app.current_tenant', '', false)"))
            connection.execute(text("SELECT set_config('app.allow_purge', '', false)"))
            connection.commit()
        except Exception:
            pass
        connection.close()


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def audit(db: Session, request: Request | None, action: str, admin: PlatformAdmin | None = None,
          username: str | None = None, tenant=None, target: str | None = None,
          detail: dict | None = None) -> None:
    """Add an audit row to the current transaction (the caller commits)."""
    db.add(PlatformAuditLog(
        admin_id=admin.id if admin else None,
        username=(admin.username if admin else username),
        action=action,
        tenant_ref=getattr(tenant, "id", None),
        tenant_slug=getattr(tenant, "slug", None),
        target=target, detail=detail,
        ip=client_ip(request) if request else None))


# ----------------------------------------------------------------- dependencies

def require_platform_admin(request: Request, response: Response,
                           db: Session = Depends(get_platform_db)) -> PlatformAdmin:
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Platform-Request") != "1":
        raise HTTPException(status_code=403, detail="طلب غير مسموح")
    token = request.cookies.get(settings.platform_cookie_name)
    payload = decode(token, SCOPE_SESSION) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="انتهت الجلسة، سجّل الدخول مجدداً")
    started = int(payload.get("st") or 0)                  # ms
    if time.time() * 1000 - started > settings.platform_session_max_hours * 3600 * 1000:
        raise HTTPException(status_code=401, detail="انتهت الجلسة، سجّل الدخول مجدداً")
    admin = db.get(PlatformAdmin, int(payload["aid"]))
    if admin is None or not admin.is_active or not admin.totp_enabled:
        raise HTTPException(status_code=401, detail="انتهت الجلسة، سجّل الدخول مجدداً")
    # A password change after this session started ends it.
    if admin.password_changed_at and admin.password_changed_at.timestamp() * 1000 > started:
        raise HTTPException(status_code=401, detail="انتهت الجلسة، سجّل الدخول مجدداً")
    set_session_cookie(response, make_session_token(admin.id, started))   # sliding idle timeout
    return admin


def temp_password(length: int = 12) -> str:
    """Readable temporary password (no 0/O/1/l/I)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in pw) and any(c.isupper() for c in pw) and any(c.islower() for c in pw):
            return pw
