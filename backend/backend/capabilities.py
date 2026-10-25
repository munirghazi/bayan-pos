"""Phase 3: per-tenant capability enforcement (donation / trade / mixed)."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db


def get_tenant_caps(request: Request, db: Session = Depends(get_db)) -> dict:
    """Read the current tenant's business_type + capability flags."""
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="غير مصرح")
    row = db.execute(text(
        "SELECT business_type, sales_enabled, donations_enabled, purchasing_enabled, "
        "vat_enabled, inventory_enabled, verification_status "
        "FROM tenants WHERE id = :i"), {"i": tid}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="الجهة غير موجودة")
    return dict(row)


def _require(flag: str, message: str):
    def dep(caps: dict = Depends(get_tenant_caps)) -> dict:
        if not caps.get(flag):
            raise HTTPException(status_code=403, detail=message)
        return caps
    return dep


require_sales = _require("sales_enabled", "البيع غير مُفعّل لهذه الجهة")
require_donations = _require("donations_enabled", "التبرّعات غير مُفعّلة لهذه الجهة")
require_purchasing = _require("purchasing_enabled", "المشتريات غير مُفعّلة لهذه الجهة")


# --- Invoice identity requirement (trade/mixed must have complete ZATCA data) ---
_INVOICE_REQUIRED = [
    ("vat_number", "الرقم الضريبي"),
    ("building_number", "رقم المبنى"),
    ("street_name", "اسم الشارع"),
    ("district", "الحي"),
    ("city", "المدينة"),
    ("postal_code", "الرمز البريدي"),
]


def require_invoice_identity(request: Request, db: Session = Depends(get_db)) -> None:
    """Block issuing an invoice until the seller identity + national address are complete.
    Applies to any sales-enabled (trade/mixed) tenant. VAT number falls back to the
    onboarding record; structured address must be set in Settings."""
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="غير مصرح")
    ts = db.execute(text(
        "SELECT vat_number, building_number, street_name, district, city, postal_code "
        "FROM tenant_settings WHERE tenant_id = :t"), {"t": tid}).mappings().first()
    eff = dict(ts) if ts else {}
    if not (eff.get("vat_number") or "").strip():
        t = db.execute(text("SELECT vat_number FROM tenants WHERE id = :t"),
                       {"t": tid}).mappings().first()
        if t and (t.get("vat_number") or "").strip():
            eff["vat_number"] = t["vat_number"]
    missing = [label for field, label in _INVOICE_REQUIRED if not (eff.get(field) or "").strip()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="لا يمكن إصدار فاتورة قبل استكمال بيانات الجهة والعنوان الوطني في الإعدادات: "
                   + "، ".join(missing))
