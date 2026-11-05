"""Release 2a — organization (entity) types and their registration numbers.

The entity type is the LEGAL form of the organization (جمعية أهلية، شركة …).
It is separate from `business_type` / the capability flags, which describe how
the tenant OPERATES (sales, donations …). The type decides:
  * which registration number applies (licence / CR / freelance document);
  * whether donations are allowed at all (non-profit types only);
  * the default thank-you line printed on receipts.

Identity (type, legal names, registration numbers, VAT registration, VAT rate)
is controlled by the platform, not by the tenant's own admin.
"""
import re

NONPROFIT, COMMERCIAL, OTHER = "nonprofit", "commercial", "other"

# key: (Arabic label, group, primary registration field or None)
ENTITY_TYPES = {
    "nonprofit_association": ("جمعية أهلية", NONPROFIT, "license_number"),
    "nonprofit_foundation": ("مؤسسة أهلية", NONPROFIT, "license_number"),
    "endowment": ("وقف", NONPROFIT, "license_number"),
    "cooperative": ("جمعية تعاونية", NONPROFIT, "license_number"),
    "company": ("شركة", COMMERCIAL, "cr_number"),
    "sole_establishment": ("مؤسسة فردية", COMMERCIAL, "cr_number"),
    "online_store": ("متجر إلكتروني", COMMERCIAL, "cr_number"),
    "freelancer": ("عمل حر", COMMERCIAL, "freelance_doc_number"),
    "other": ("أخرى", OTHER, None),
}
DEFAULT_TYPE = "nonprofit_association"

REG_LABELS = {
    "unified_number": "الرقم الموحد",
    "cr_number": "رقم السجل التجاري",
    "license_number": "رقم الترخيص",
    "freelance_doc_number": "رقم وثيقة العمل الحر",
}

THANKS = {
    NONPROFIT: "جزاكم الله خيراً",
    COMMERCIAL: "شكراً لتسوقكم معنا",
    OTHER: "شكراً لتعاملكم معنا",
}

UNIFIED_RE = re.compile(r"^7\d{9}$")
VAT_RE = re.compile(r"^3\d{13}3$")
SHORT_ADDRESS_RE = re.compile(r"^[A-Z]{4}\d{4}$")


def info(entity_type: str | None) -> dict:
    key = entity_type if entity_type in ENTITY_TYPES else DEFAULT_TYPE
    label, group, primary = ENTITY_TYPES[key]
    return {"entity_type": key, "entity_type_label": label, "entity_group": group,
            "primary_registration": primary,
            "primary_registration_label": REG_LABELS.get(primary) if primary else None}


def is_nonprofit(entity_type: str | None) -> bool:
    return info(entity_type)["entity_group"] == NONPROFIT


def validate_identity(fields: dict) -> list[str]:
    """Format checks for platform-set identity. Returns a list of Arabic errors."""
    errs = []
    et = fields.get("entity_type")
    if et is not None and et not in ENTITY_TYPES:
        errs.append("نوع المنشأة غير معروف")
    un = (fields.get("unified_number") or "").strip()
    if un and not UNIFIED_RE.match(un):
        errs.append("الرقم الموحد: 10 أرقام يبدأ بالرقم 7")
    vat = (fields.get("vat_number") or "").strip()
    if vat and not VAT_RE.match(vat):
        errs.append("الرقم الضريبي: 15 رقماً يبدأ وينتهي بالرقم 3")
    rate = fields.get("vat_rate")
    if rate is not None and not (0 <= float(rate) <= 100):
        errs.append("نسبة الضريبة غير صحيحة")
    return errs
