"""Phase 3: per-tenant capability enforcement (donation / trade / mixed)."""
import re

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
        "vat_enabled, inventory_enabled, verification_status, entity_type "
        "FROM tenants WHERE id = :i"), {"i": tid}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="المنشأة غير موجودة")
    import entities
    caps = dict(row)
    ent = entities.info(caps.get("entity_type"))
    caps.update(entity_type=ent["entity_type"], entity_type_label=ent["entity_type_label"],
                entity_group=ent["entity_group"])
    # Donations exist only for non-profit organizations, whatever the flag says.
    caps["donations_enabled"] = bool(caps["donations_enabled"]) and ent["entity_group"] == entities.NONPROFIT
    return caps


def _require(flag: str, message: str):
    def dep(caps: dict = Depends(get_tenant_caps)) -> dict:
        if not caps.get(flag):
            raise HTTPException(status_code=403, detail=message)
        return caps
    return dep


require_sales = _require("sales_enabled", "البيع غير مُفعّل لهذه المنشأة")
require_donations = _require("donations_enabled", "التبرّعات غير مُفعّلة لهذه المنشأة")
require_purchasing = _require("purchasing_enabled", "المشتريات غير مُفعّلة لهذه المنشأة")


# --- Invoice identity requirement (trade/mixed must have complete ZATCA data) ---
_INVOICE_REQUIRED = [
    ("vat_number", "الرقم الضريبي"),
    ("building_number", "رقم المبنى"),
    ("street_name", "اسم الشارع"),
    ("district", "الحي"),
    ("city", "المدينة"),
    ("postal_code", "الرمز البريدي"),
]


def invoice_identity_gaps(db, tid) -> dict:
    """What still blocks issuing invoices, split by who can fix it:
    address  -> the tenant admin (Settings → national address)
    platform -> the platform admin (VAT number is platform-controlled)"""
    ts = db.execute(text(
        "SELECT building_number, street_name, district, city, postal_code, vat_number "
        "FROM tenant_settings WHERE tenant_id = :t"), {"t": tid}).mappings().first()
    eff = dict(ts) if ts else {}
    t = db.execute(text("SELECT vat_enabled, vat_number FROM tenants WHERE id = :t"), {"t": tid}).mappings().first()
    address = [label for field, label in _INVOICE_REQUIRED[1:] if not (eff.get(field) or "").strip()]
    platform = []
    if t and t["vat_enabled"]:
        # platform-controlled number first; the settings copy is the legacy fallback
        vat = (t["vat_number"] or eff.get("vat_number") or "").strip()
        if not vat:
            platform.append("الرقم الضريبي غير مسجّل للمنشأة")
        elif not re.fullmatch(r"3\d{13}3", vat):
            platform.append("الرقم الضريبي المسجّل غير صحيح")
    return {"address": address, "platform": platform, "ready": not address and not platform}


def require_invoice_identity(request: Request, db: Session = Depends(get_db)) -> None:
    """Block issuing an invoice until the seller identity + national address are complete."""
    tid = getattr(request.state, "tenant_id", None)
    if tid is None:
        raise HTTPException(status_code=401, detail="غير مصرح")
    gaps = invoice_identity_gaps(db, tid)
    if gaps["platform"]:
        raise HTTPException(status_code=400, detail=(
            "لا يمكن إصدار فاتورة: " + "، ".join(gaps["platform"])
            + ". الرقم الضريبي تضبطه إدارة المنصة — تواصل معها لتصحيحه."))
    if gaps["address"]:
        raise HTTPException(status_code=400, detail=(
            "لا يمكن إصدار فاتورة قبل استكمال العنوان الوطني في الإعدادات. الناقص: "
            + "، ".join(gaps["address"])))
