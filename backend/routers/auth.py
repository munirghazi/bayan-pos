from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db, User, Tenant
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


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    must_change_password: bool = False

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    password: str | None = None


# ===================== Helpers =====================

def create_access_token(*, username: str, tenant_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": username, "tid": tenant_id, "exp": expire}
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

@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    # Resolve tenant (tenants table is not RLS-protected).
    tenant_q = db.query(Tenant).filter(Tenant.is_active == True)  # noqa: E712
    if request.tenant:
        tenant = tenant_q.filter(Tenant.slug == request.tenant).first()
    else:
        tenants = tenant_q.limit(2).all()
        tenant = tenants[0] if len(tenants) == 1 else None
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="يجب تحديد الجهة (tenant)")

    # Pin this connection to the tenant so the user lookup is RLS-scoped.
    _pin_session_tenant(db, tenant.id)

    user = db.query(User).filter(User.username == request.username).first()
    if not user or not pwd_context.verify(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="الحساب معطل")

    token = create_access_token(username=user.username, tenant_id=tenant.id)
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token, token_type="bearer",
                         user=UserResponse.model_validate(user))


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/", domain=settings.cookie_domain)
    return {"message": "تم تسجيل الخروج"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return db.query(User).all()


@router.post("/users", response_model=UserResponse)
def create_user(request: UserCreate, db: Session = Depends(get_db),
                current_user: User = Depends(require_admin)):
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="اسم المستخدم موجود مسبقاً")
    user = User(
        username=request.username,
        password_hash=pwd_context.hash(request.password),
        full_name=request.full_name,
        role=request.role,
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
    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.password is not None:
        user.password_hash = pwd_context.hash(request.password)
        user.must_change_password = False
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
    db.delete(user)
    db.commit()
    return {"message": "تم حذف المستخدم بنجاح"}
