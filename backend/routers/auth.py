from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db, User, Tenant, Location
from tenancy import get_secret_key

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# ===================== Schemas =====================

class LoginRequest(BaseModel):
    username: str
    password: str
    tenant: str | None = None   # tenant slug; optional when only one tenant exists


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "cashier"
    location_id: int | None = None
    permissions: list[str] | None = None     # non-admin: ticked permissions (default: role template)


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    role_label: str = ""
    is_active: bool
    must_change_password: bool = False
    location_id: int | None = None
    permissions: list[str] = []               # effective (admin: all)

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _effective(cls, v):
        if isinstance(v, dict) or not hasattr(v, "role"):
            return v
        import perms
        return {"id": v.id, "username": v.username, "full_name": v.full_name, "role": v.role,
                "role_label": perms.ROLE_LABELS.get(v.role, v.role), "is_active": bool(v.is_active),
                "must_change_password": bool(v.must_change_password), "location_id": v.location_id,
                "permissions": perms.effective(v)}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    tenant_slug: str | None = None
    tenant_name: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None
    location_id: int | None = None
    permissions: list[str] | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _validate_location(db, location_id):
    if location_id is None:
        return
    if not db.query(Location).filter(Location.id == location_id).first():
        raise HTTPException(status_code=400, detail="الفرع غير موجود")


# ===================== Helpers =====================

def create_access_token(*, username: str, tenant_id: int) -> str:
    import time as _time
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "tid": tenant_id, "exp": expire, "iat_ms": int(_time.time() * 1000)}
    return jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM)


def _pin_session_tenant(db: Session, tenant_id: int) -> None:
    """Pin THIS session's connection to a tenant (used pre-auth in /login)."""
    db.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
               {"t": str(int(tenant_id))})


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the caller from request.state populated by get_db."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="بيانات الدخول غير صحيحة",
        headers={"WWW-Authenticate": "Bearer"},
    )
    username = getattr(request.state, "username", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    if not username or tenant_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    # Ended by logout / password change / reset (security test AUTH-15).
    if user.tokens_valid_after is not None:
        iat_ms = getattr(request.state, "token_iat_ms", 0) or 0
        if iat_ms < user.tokens_valid_after.timestamp() * 1000:
            raise credentials_exception
    # A tenant suspended from the platform console loses its open sessions too.
    active = db.execute(text("SELECT is_active FROM tenants WHERE id = :i"), {"i": tenant_id}).scalar()
    if not active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="المنشأة موقوفة. تواصل مع إدارة المنصة.")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="صلاحية المدير مطلوبة")
    return current_user


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


# ===================== Routes =====================


def _register_failed_login(db, tenant_slug, username, att, cfg):
    from sqlalchemy import text as _t
    if att:
        newc = (att.failed_count or 0) + 1
        locked = None
        if newc >= cfg.max_login_attempts:
            locked = datetime.utcnow() + timedelta(minutes=cfg.lockout_minutes)
        db.execute(_t("UPDATE login_attempts SET failed_count=:c, locked_until=:l, updated_at=now() WHERE id=:i"),
                   {"c": newc, "l": locked, "i": att.id})
    else:
        db.execute(_t("INSERT INTO login_attempts (tenant_slug, username, failed_count) VALUES (:s,:u,1)"),
                   {"s": tenant_slug, "u": username})
    db.commit()


def _clear_failed_login(db, tenant_slug, username):
    from sqlalchemy import text as _t
    db.execute(_t("UPDATE login_attempts SET failed_count=0, locked_until=NULL, updated_at=now() "
                  "WHERE tenant_slug=:s AND username=:u"), {"s": tenant_slug, "u": username})
    db.commit()


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # A tenant must always be specified (multi-organization; no auto-pick).
    if not request.tenant:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="يجب تحديد اسم المنشأة")
    tenant = db.query(Tenant).filter(
        Tenant.slug == request.tenant, Tenant.is_active == True).first()  # noqa: E712
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="المنشأة غير موجودة أو غير مفعّلة")

    # Pin this connection to the tenant so the user lookup is RLS-scoped.
    _pin_session_tenant(db, tenant.id)

    # --- brute-force protection: check lock, then verify ---
    from config import settings as _cfg
    att = db.execute(text(
        "SELECT id, failed_count, locked_until FROM login_attempts "
        "WHERE tenant_slug=:s AND username=:u"),
        {"s": request.tenant, "u": request.username}).first()
    if att and att.locked_until and att.locked_until > datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="تم قفل الحساب مؤقتاً بسبب محاولات دخول متكررة. حاول لاحقاً.")

    user = db.query(User).filter(User.username == request.username).first()
    if not user or not pwd_context.verify(request.password, user.password_hash):
        _register_failed_login(db, request.tenant, request.username, att, _cfg)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="الحساب معطل")
    _clear_failed_login(db, request.tenant, request.username)

    token = create_access_token(username=user.username, tenant_id=tenant.id)
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token, token_type="bearer",
                         user=UserResponse.model_validate(user),
                         tenant_slug=tenant.slug, tenant_name=tenant.name)


def end_sessions(user: User) -> None:
    """Every token issued before now stops working (all devices of this user)."""
    from datetime import timezone as _tz
    user.tokens_valid_after = datetime.now(_tz.utc)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    username = getattr(request.state, "username", None)
    if username and getattr(request.state, "tenant_id", None) is not None:
        user = db.query(User).filter(User.username == username).first()
        if user is not None:
            end_sessions(user)
            db.commit()
    response.delete_cookie(settings.cookie_name, path="/", domain=settings.cookie_domain)
    return {"message": "تم تسجيل الخروج"}

@router.get("/capabilities")
def capabilities(request: Request, db: Session = Depends(get_db),
                 current_user: "User" = Depends(get_current_user)):
    """Tenant business_type + capability flags, for the frontend to adapt the UI."""
    from capabilities import get_tenant_caps
    return get_tenant_caps(request, db)



@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(request: ChangePasswordRequest, response: Response, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    """Self-service password change for the logged-in user. Also clears the
    must_change_password flag (used by the forced first-login change)."""
    if not pwd_context.verify(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="كلمة المرور الحالية غير صحيحة")
    if len(request.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل")
    if request.new_password == request.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="كلمة المرور الجديدة يجب أن تختلف عن الحالية")
    current_user.password_hash = pwd_context.hash(request.new_password)
    current_user.must_change_password = False
    end_sessions(current_user)               # other devices are logged out …
    db.commit()
    token = create_access_token(username=current_user.username, tenant_id=current_user.tenant_id)
    _set_auth_cookie(response, token)        # … this one continues with a fresh session
    return {"message": "تم تغيير كلمة المرور بنجاح", "access_token": token}


@router.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return db.query(User).all()


def _role_and_permissions(role: str | None, permissions: list[str] | None):
    import perms
    role = (role or "cashier").strip()
    if role not in perms.ROLES:
        raise HTTPException(status_code=400, detail="الدور غير معروف")
    if role == "admin":
        return "admin", None
    if permissions is None:
        permissions = perms.TEMPLATES[role][1] if role in perms.TEMPLATES else []
    unknown = [p for p in permissions if p not in perms.CATALOG]
    if unknown:
        raise HTTPException(status_code=400, detail="صلاحيات غير معروفة: " + "، ".join(unknown))
    permissions = perms.clean(permissions)
    if not permissions:
        raise HTTPException(status_code=400, detail="اختر صلاحية واحدة على الأقل")
    return role, permissions


def _ensure_another_admin(db: Session, user: User) -> None:
    others = db.query(User).filter(User.role == "admin", User.is_active == True, User.id != user.id).count()  # noqa: E712
    if others == 0:
        raise HTTPException(status_code=400, detail="يجب أن يبقى مدير نظام واحد على الأقل")


@router.get("/permissions")
def permissions_catalog(current_user: User = Depends(get_current_user)):
    import perms
    return perms.catalog_out()


@router.post("/users", response_model=UserResponse)
def create_user(request: UserCreate, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقاً")
    _validate_location(db, request.location_id)
    role, permissions = _role_and_permissions(request.role, request.permissions)
    if len(request.password or "") < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")
    user = User(
        username=request.username,
        password_hash=pwd_context.hash(request.password),
        full_name=request.full_name,
        role=role,
        permissions=permissions,
        location_id=request.location_id,
        must_change_password=True,          # the person sets their own password at first login
    )  # tenant_id filled by DB default from app.current_tenant
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, request: UserUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if request.full_name is not None:
        user.full_name = request.full_name
    if request.role is not None or request.permissions is not None:
        role, permissions = _role_and_permissions(request.role or user.role,
                                                  request.permissions if request.permissions is not None
                                                  else (None if request.role and request.role != user.role else user.permissions))
        if user.id == current_user.id and role != "admin":
            raise HTTPException(status_code=400, detail="لا يمكنك إزالة صلاحية المدير عن حسابك")
        if user.role == "admin" and role != "admin":
            _ensure_another_admin(db, user)
        if (role, permissions) != (user.role, user.permissions):
            end_sessions(user)              # new permissions take effect at the next login
        user.role, user.permissions = role, permissions
    if request.is_active is not None:
        if not request.is_active and user.id == current_user.id:
            raise HTTPException(status_code=400, detail="لا يمكنك تعطيل حسابك")
        if not request.is_active and user.role == "admin":
            _ensure_another_admin(db, user)
        user.is_active = request.is_active
        if not request.is_active:
            end_sessions(user)
    if request.password is not None:
        user.password_hash = pwd_context.hash(request.password)
        user.must_change_password = False
        if user.id != current_user.id:
            end_sessions(user)
    if request.location_id is not None:
        _validate_location(db, request.location_id)
        user.location_id = request.location_id
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="لا يمكنك حذف حسابك الخاص")
    if user.role == "admin":
        _ensure_another_admin(db, user)
    db.delete(user)
    db.commit()
    return {"message": "تم حذف المستخدم بنجاح"}
