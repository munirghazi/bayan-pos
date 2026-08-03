import os
import glob
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, TenantSettings
from routers.auth import get_current_user, require_admin, User

router = APIRouter()

UPLOADS_DIR = "uploads"
LOGO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


# ===================== Schemas =====================

class TenantSettingsResponse(BaseModel):
    seller_name: str | None = None
    vat_number: str | None = None
    national_address: str | None = None
    vat_rate: float = 15.0
    city: str | None = None
    country: str | None = None
    website: str | None = None
    logo_url: str | None = None
    payment_methods: str = "cash,card,transfer"
    inventory_mode: str = "per_branch"

    class Config:
        from_attributes = True


class TenantSettingsUpdate(BaseModel):
    seller_name: str | None = None
    vat_number: str | None = None
    national_address: str | None = None
    vat_rate: float | None = None
    city: str | None = None
    country: str | None = None
    website: str | None = None
    payment_methods: str | None = None


def _get_or_create(db: Session) -> TenantSettings:
    row = db.query(TenantSettings).first()   # RLS scopes to the caller's tenant
    if row is None:
        row = TenantSettings()               # tenant_id filled by DB default
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


# ===================== Tenant profile =====================

@router.get("/tenant", response_model=TenantSettingsResponse)
def get_tenant_settings(db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    return _get_or_create(db)


@router.put("/tenant", response_model=TenantSettingsResponse)
def update_tenant_settings(req: TenantSettingsUpdate, db: Session = Depends(get_db),
                           current_user: User = Depends(require_admin)):
    row = _get_or_create(db)
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


# ===================== Per-tenant logo =====================

@router.post("/upload-logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db),
                      current_user: User = Depends(require_admin)):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in LOGO_EXTS:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")

    tenant_dir = os.path.join(UPLOADS_DIR, f"tenant_{current_user.tenant_id}")
    os.makedirs(tenant_dir, exist_ok=True)

    # remove previous logo(s) for this tenant
    for old in glob.glob(os.path.join(tenant_dir, "logo_*")):
        try:
            os.remove(old)
        except OSError:
            pass

    filename = f"logo_{uuid.uuid4().hex}{ext}"
    with open(os.path.join(tenant_dir, filename), "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    url = f"/uploads/tenant_{current_user.tenant_id}/{filename}"
    row = _get_or_create(db)
    row.logo_url = url
    db.commit()
    return {"url": url}


@router.get("/logo")
def get_logo(db: Session = Depends(get_db)):
    # No auth required: on the login screen there is no tenant yet, so this
    # must NOT 401 (a 401 here triggers the app's redirect-to-login loop).
    # With a valid session, get_db pins the tenant and RLS returns its logo;
    # without one, RLS yields no row and we return an empty URL.
    row = db.query(TenantSettings).first()
    return {"url": (row.logo_url if row and row.logo_url else "")}
