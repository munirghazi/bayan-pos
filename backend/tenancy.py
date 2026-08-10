"""JWT helpers used to resolve the tenant from each request."""
from jose import JWTError, jwt
from starlette.requests import Request

from config import settings

_DEV_SECRET = None


def get_secret_key() -> str:
    """JWT secret. Required in production; ephemeral per-process key in dev."""
    global _DEV_SECRET
    if settings.secret_key:
        return settings.secret_key
    if settings.is_production:
        raise RuntimeError("SECRET_KEY is not set. Refusing to start in production without it.")
    if _DEV_SECRET is None:
        import os
        import secrets as _s
        # Persist the dev secret so restarting the server doesn't invalidate
        # everyone's session (which manifests as sudden 401s / a login loop).
        path = os.path.join(os.path.dirname(__file__), ".dev_secret")
        try:
            if os.path.exists(path):
                _DEV_SECRET = open(path).read().strip() or None
            if not _DEV_SECRET:
                _DEV_SECRET = _s.token_urlsafe(48)
                with open(path, "w") as f:
                    f.write(_DEV_SECRET)
        except Exception:
            _DEV_SECRET = _DEV_SECRET or _s.token_urlsafe(48)
    return _DEV_SECRET


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_secret_key(), algorithms=[settings.algorithm])
    except JWTError:
        return None


def extract_token(request: Request) -> str | None:
    token = request.cookies.get(settings.cookie_name)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None
