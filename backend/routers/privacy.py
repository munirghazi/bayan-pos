"""Wave 3 — PDPL data-subject features.

Right of access / portability : export a customer's personal data.
Right to erasure              : anonymise a customer's PII while retaining the
                               transactional/financial records that tax law
                               (ZATCA) requires be kept — erasure ≠ hard delete.
Right to rectification        : handled by the existing PUT /customers/{id}.
Retention                     : preview and apply anonymisation for customers
                               with no activity beyond the tenant's retention window.

All actions are admin-only and audited (tenant_audit_log).
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Customer, Sale, Donation, TenantSettings
from routers.auth import require_admin, User
from tenant_audit import tenant_audit

router = APIRouter()  # mounted at /api/privacy

ANON_NAME = "عميل محذوف"


def _anonymise(c: Customer) -> None:
    c.name = ANON_NAME
    c.phone = None
    c.email = None
    c.vat_number = None
    c.address = None
    c.city = None
    c.erased_at = datetime.utcnow()


def _customer_or_404(db, customer_id):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    return c


# ---------- Right of access / portability ----------
@router.get("/customer/{customer_id}/export")
def export_customer(customer_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    c = _customer_or_404(db, customer_id)
    sales = db.query(Sale).filter(Sale.customer_id == customer_id).all()
    tenant_audit(db, user, "pdpl_export", target=customer_id)
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "customer": {
            "id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
            "vat_number": c.vat_number, "address": c.address, "city": c.city,
            "erased_at": c.erased_at.isoformat() if c.erased_at else None,
        },
        "transactions": [
            {"sale_id": s.id, "created_at": s.created_at.isoformat() if s.created_at else None,
             "total": s.total} for s in sales
        ],
        "note": "Transactional/financial records are retained for tax compliance; "
                "personal identifiers can be erased via the erasure endpoint.",
    }


# ---------- Right to erasure ----------
@router.post("/customer/{customer_id}/erase")
def erase_customer(customer_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    c = _customer_or_404(db, customer_id)
    if c.erased_at:
        return {"message": "سبق محو بيانات هذا العميل", "customer_id": customer_id,
                "erased_at": c.erased_at.isoformat()}
    _anonymise(c)
    db.commit()
    tenant_audit(db, user, "pdpl_erase", target=customer_id)
    return {"message": "تم محو البيانات الشخصية مع الاحتفاظ بالسجلات المالية",
            "customer_id": customer_id, "erased_at": c.erased_at.isoformat()}


class DonorErase(BaseModel):
    name: str


@router.post("/donor/erase")
def erase_donor(req: DonorErase, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    """Anonymise donor identifiers on donations matching a free-text name."""
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="الاسم مطلوب")
    rows = db.query(Donation).filter(Donation.donor_name == name).all()
    for d in rows:
        d.donor_name = None
        d.note = None
    db.commit()
    tenant_audit(db, user, "pdpl_donor_erase", detail=f"count={len(rows)}")
    return {"message": "تم محو بيانات المتبرع", "affected": len(rows)}


# ---------- Retention ----------
def _retention_window_months(db, override):
    if override is not None:
        return override
    st = db.query(TenantSettings).first()
    return st.data_retention_months if st else None


def _eligible_for_retention(db, months):
    cutoff = datetime.utcnow() - timedelta(days=30 * months)
    out = []
    for c in db.query(Customer).filter(Customer.erased_at.is_(None)).all():
        last = (db.query(Sale.created_at)
                  .filter(Sale.customer_id == c.id)
                  .order_by(Sale.created_at.desc()).first())
        last_dt = last[0] if last else None
        if last_dt is None or last_dt < cutoff:
            out.append((c, last_dt))
    return cutoff, out


@router.get("/retention/preview")
def retention_preview(months: int | None = None, db: Session = Depends(get_db),
                      user: User = Depends(require_admin)):
    m = _retention_window_months(db, months)
    if not m or m <= 0:
        raise HTTPException(status_code=400,
                            detail="لم تُحدَّد مدة الاحتفاظ (data_retention_months)")
    cutoff, rows = _eligible_for_retention(db, m)
    return {
        "retention_months": m,
        "cutoff": cutoff.isoformat(),
        "eligible_count": len(rows),
        "customers": [{"id": c.id, "name": c.name,
                       "last_activity": (ld.isoformat() if ld else None)} for c, ld in rows],
    }


@router.post("/retention/apply")
def retention_apply(months: int | None = None, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    m = _retention_window_months(db, months)
    if not m or m <= 0:
        raise HTTPException(status_code=400,
                            detail="لم تُحدَّد مدة الاحتفاظ (data_retention_months)")
    _, rows = _eligible_for_retention(db, m)
    for c, _ld in rows:
        _anonymise(c)
    db.commit()
    tenant_audit(db, user, "pdpl_retention", detail=f"months={m} erased={len(rows)}")
    return {"message": "تم تطبيق سياسة الاحتفاظ", "retention_months": m, "erased": len(rows)}
