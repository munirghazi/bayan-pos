import os
import glob
import shutil
import uuid

from datetime import date
import re

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, TenantSettings, Tenant
from routers.auth import get_current_user, require_admin, User

router = APIRouter()

UPLOADS_DIR = "uploads"
LOGO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}


# ===================== Schemas =====================

class TenantSettingsResponse(BaseModel):
    # ---- identity (platform-controlled, read-only here)
    entity_type: str | None = None
    entity_type_label: str | None = None
    entity_group: str | None = None
    primary_registration: str | None = None
    name_en: str | None = None
    unified_number: str | None = None
    cr_number: str | None = None
    license_number: str | None = None
    freelance_doc_number: str | None = None
    vat_enabled: bool = True
    # ---- national address extras (Release 2a)
    short_address: str | None = None
    street_name_en: str | None = None
    district_en: str | None = None
    city_en: str | None = None
    country_en: str | None = None
    address_proof_number: str | None = None
    address_proof_expiry: date | None = None
    show_en_address: bool = False
    receipt_thanks: str | None = None
    default_thanks: str | None = None
    seller_name: str | None = None
    vat_number: str | None = None
    national_address: str | None = None
    vat_rate: float = 15.0
    city: str | None = None
    country: str | None = None
    building_number: str | None = None
    street_name: str | None = None
    district: str | None = None
    postal_code: str | None = None
    additional_number: str | None = None
    region: str | None = None
    website: str | None = None
    logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    brand_name: str | None = None
    font_family: str | None = None
    ui_radius: str | None = None
    receipt_footer: str | None = None
    show_powered_by: bool = True
    payment_methods: str = "cash,card,transfer"
    require_transfer_proof: bool = True
    data_retention_months: int | None = None
    inventory_mode: str = "per_branch"

    class Config:
        from_attributes = True


IDENTITY_FIELDS = {"seller_name", "vat_number", "vat_rate"}   # platform-controlled


class TenantSettingsUpdate(BaseModel):
    # identity fields are accepted only to give a clear 403 (see update_tenant_settings)
    seller_name: str | None = None
    vat_number: str | None = None
    vat_rate: float | None = None
    national_address: str | None = None
    short_address: str | None = None
    street_name_en: str | None = None
    district_en: str | None = None
    city_en: str | None = None
    country_en: str | None = None
    address_proof_number: str | None = None
    address_proof_expiry: date | None = None
    show_en_address: bool | None = None
    receipt_thanks: str | None = None
    city: str | None = None
    country: str | None = None
    building_number: str | None = None
    street_name: str | None = None
    district: str | None = None
    postal_code: str | None = None
    additional_number: str | None = None
    region: str | None = None
    website: str | None = None
    payment_methods: str | None = None
    require_transfer_proof: bool | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    brand_name: str | None = None
    font_family: str | None = None
    ui_radius: str | None = None
    receipt_footer: str | None = None
    data_retention_months: int | None = None


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
def get_tenant_settings(request: Request, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    row = _get_or_create(db)
    tid = getattr(request.state, "tenant_id", None)
    return _settings_response(db, row, tid)


def _settings_response(db, row, tid):
    # Fall back to the identity captured at onboarding (tenants table) when the
    # invoice settings haven't been filled in yet, so invoices are never blank.
    import entities
    t = db.query(Tenant).filter(Tenant.id == tid).first() if tid else None
    ent = entities.info(getattr(t, "entity_type", None))
    return TenantSettingsResponse(
        **ent,
        name_en=getattr(t, "name_en", None),
        unified_number=getattr(t, "unified_number", None),
        cr_number=getattr(t, "cr_number", None),
        license_number=getattr(t, "license_number", None),
        freelance_doc_number=getattr(t, "freelance_doc_number", None),
        vat_enabled=bool(getattr(t, "vat_enabled", True)) if t else True,
        short_address=row.short_address,
        street_name_en=row.street_name_en,
        district_en=row.district_en,
        city_en=row.city_en,
        country_en=row.country_en,
        address_proof_number=row.address_proof_number,
        address_proof_expiry=row.address_proof_expiry,
        show_en_address=bool(row.show_en_address),
        receipt_thanks=row.receipt_thanks,
        default_thanks=entities.THANKS[ent["entity_group"]],
        # legal name + VAT number: the platform record first (settings = legacy)
        seller_name=(t.name if t and t.name else row.seller_name),
        vat_number=((t.vat_number if t else None) or row.vat_number),
        national_address=row.national_address or (t.national_address if t else None),
        vat_rate=row.vat_rate if row.vat_rate is not None else 15.0,
        city=row.city,
        country=row.country,
        building_number=row.building_number,
        street_name=row.street_name,
        district=row.district,
        postal_code=row.postal_code,
        additional_number=row.additional_number,
        region=row.region,
        website=row.website,
        logo_url=row.logo_url,
        favicon_url=row.favicon_url,
        primary_color=row.primary_color,
        accent_color=row.accent_color,
        brand_name=row.brand_name,
        font_family=row.font_family,
        ui_radius=row.ui_radius,
        payment_methods=row.payment_methods or "cash,card,transfer",
        require_transfer_proof=bool(getattr(row, "require_transfer_proof", True)),
        data_retention_months=row.data_retention_months,
        inventory_mode=row.inventory_mode or "per_branch",
        receipt_footer=row.receipt_footer,
        show_powered_by=(t.show_powered_by if t is not None else True),
    )


@router.put("/tenant", response_model=TenantSettingsResponse)
def update_tenant_settings(request: Request, req: TenantSettingsUpdate, db: Session = Depends(get_db),
                           current_user: User = Depends(require_admin)):
    import entities
    row = _get_or_create(db)
    tid = getattr(request.state, "tenant_id", None)
    data = req.model_dump(exclude_unset=True)

    # Identity is platform-controlled: refuse changes, tolerate the unchanged value.
    current = _settings_response(db, row, tid)
    changed = [f for f in IDENTITY_FIELDS & data.keys()
               if (data[f] or None) != (getattr(current, f) or None)
               and not (f == "vat_rate" and data[f] is not None and float(data[f]) == float(current.vat_rate))]
    if changed:
        raise HTTPException(status_code=403,
                            detail="الاسم النظامي والرقم الضريبي ونسبة الضريبة تُعدَّل من إدارة المنصة")
    for f in IDENTITY_FIELDS:
        data.pop(f, None)

    # National address formats (same rules as the official address proof)
    def bad(field, pattern, msg):
        v = data.get(field)
        if v not in (None, "") and not re.fullmatch(pattern, str(v).strip()):
            raise HTTPException(status_code=400, detail=msg)
    if data.get("short_address"):
        data["short_address"] = data["short_address"].strip().upper().replace(" ", "")
    bad("short_address", r"[A-Z]{4}\d{4}", "العنوان المختصر: 4 حروف إنجليزية ثم 4 أرقام (مثل JBRA6522)")
    bad("building_number", r"\d{4}", "رقم المبنى: 4 أرقام")
    bad("additional_number", r"\d{4}", "الرقم الفرعي: 4 أرقام")
    bad("postal_code", r"\d{5}", "الرمز البريدي: 5 أرقام")

    for field, value in data.items():
        setattr(row, field, (value.strip() or None) if isinstance(value, str) else value)
    db.commit()
    db.refresh(row)
    tid = getattr(request.state, "tenant_id", None)
    return _settings_response(db, row, tid)


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
