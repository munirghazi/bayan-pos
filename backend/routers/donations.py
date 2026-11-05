"""Donations — issued as a DONATION RECEIPT (إيصال تبرع), never as a tax invoice.

Rules (Release 1):
* payment by card (POS terminal) or bank transfer only — cash is refused;
* a donation is its own transaction: there are no product lines here, and the
  sales endpoint has no donation fields, so the two can never be mixed;
* numbered per branch: B01-DON-000001 (gap-free, locked counter);
* never deleted — an admin may VOID a receipt with a reason; it keeps its number;
* every endpoint is unavailable when the tenant's donations flag is off.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import idempotency
import invoicing as inv
from capabilities import require_donations
from database import get_db, Donation
from routers.auth import get_current_user, require_admin, User
from routers.sales import _check_payment
from tenant_audit import tenant_audit

router = APIRouter()


# ===================== Schemas =====================

class DonationCreate(BaseModel):
    donor_name: str | None = None
    amount: float
    note: str | None = None
    payment_method: str
    card_ref: str | None = None
    proof_id: int | None = None          # bank-transfer proof (required for transfer)
    register_id: int | None = None


class DonationVoid(BaseModel):
    reason: str


class DonationResponse(BaseModel):
    id: int
    receipt_number: str
    location_id: int
    register_id: int | None = None
    donor_name: str | None
    amount: float
    note: str | None
    payment_method: str
    card_ref: str | None = None
    proof_id: int | None = None
    status: str
    void_reason: str | None = None
    voided_at: datetime | None = None
    voided_by: str | None = None
    seller: dict
    user_id: int
    user_name: str | None = None
    issued_at: datetime
    created_at: datetime


# ===================== Routes =====================

@router.post("/", response_model=DonationResponse)
def create_donation(request: DonationCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user),
                    _caps: dict = Depends(require_donations),
                    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    prior = idempotency.replay(db, idempotency_key, "donations")
    if prior is not None:
        return JSONResponse(content=prior)
    donation = issue_donation(db, request, current_user)
    _resp = _format_donation(db, donation)
    idempotency.store(db, idempotency_key, "donations", _resp)
    return _resp


def validate_donation(db, request: DonationCreate, user, draft: bool = False):
    """Donation rules. Returns (location_id, register_id)."""
    import payments as pay
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="مبلغ التبرع يجب أن يكون أكبر من صفر")
    if request.payment_method == "cash":
        raise HTTPException(status_code=400,
                            detail="لا تُقبل التبرعات نقداً — الدفع بالشبكة أو التحويل البنكي فقط")
    _check_payment(db, request.payment_method, request.card_ref, inv.DONATION_PAYMENT_METHODS)
    if request.payment_method == "transfer":
        _, require_proof = pay.tenant_payment_settings(db)
        if request.proof_id:
            pay.check_proof(db, request.proof_id)
        elif require_proof and not draft:
            raise HTTPException(status_code=400,
                                detail="أرفق إثبات التحويل البنكي أو احفظ التبرع كمسودة")
    return inv.resolve_location(db, request.register_id, user)


def issue_donation(db, request: DonationCreate, user, before_commit=None) -> Donation:
    import payments as pay
    location_id, register_id = validate_donation(db, request, user)
    alloc = inv.allocate(db, location_id, inv.DOC_DONATION)
    donation = Donation(
        location_id=location_id,
        register_id=register_id,
        receipt_number=alloc.number,
        receipt_seq=alloc.seq,
        issued_at=inv.utcnow(),
        donor_name=(request.donor_name or "").strip() or None,
        amount=inv.q2(request.amount),
        note=(request.note or "").strip() or None,
        payment_method=request.payment_method,
        card_ref=(request.card_ref or "").strip() or None,
        proof_id=request.proof_id if request.payment_method == "transfer" else None,
        status="issued",
        user_id=user.id,
    )
    db.add(donation)
    if donation.proof_id:
        pay.mark_proof_used(db, donation.proof_id, alloc.number)
    inv.commit_allocation(db, alloc, None)
    if before_commit:
        before_commit(donation)
    db.commit()
    db.refresh(donation)
    return donation


@router.get("/", response_model=list[DonationResponse])
def get_donations(skip: int = 0, limit: int = 50, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user),
                  _caps: dict = Depends(require_donations)):
    rows = (db.query(Donation).order_by(Donation.issued_at.desc(), Donation.id.desc())
              .offset(skip).limit(limit).all())
    seller = inv.seller_snapshot(db)
    return [_format_donation(db, d, seller) for d in rows]


@router.get("/{donation_id}", response_model=DonationResponse)
def get_donation(donation_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user),
                 _caps: dict = Depends(require_donations)):
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        raise HTTPException(status_code=404, detail="التبرع غير موجود")
    return _format_donation(db, donation)


@router.post("/{donation_id}/void", response_model=DonationResponse)
def void_donation(donation_id: int, req: DonationVoid, db: Session = Depends(get_db),
                  user: User = Depends(require_admin),
                  _caps: dict = Depends(require_donations)):
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="سبب الإلغاء مطلوب")
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        raise HTTPException(status_code=404, detail="التبرع غير موجود")
    if donation.status == "void":
        raise HTTPException(status_code=400, detail="الإيصال ملغى مسبقاً")
    donation.status = "void"
    donation.void_reason = reason[:300]
    donation.voided_at = inv.utcnow()
    donation.voided_by = user.username
    db.commit()
    db.refresh(donation)
    tenant_audit(db, user, "donation_void", target=donation.receipt_number, detail=reason[:200])
    return _format_donation(db, donation)


@router.delete("/{donation_id}")
def delete_donation(donation_id: int, current_user: User = Depends(get_current_user)):
    raise HTTPException(status_code=405,
                        detail="لا يمكن حذف إيصال تبرع صادر — استخدم الإلغاء مع ذكر السبب")


def _format_donation(db: Session, donation: Donation, seller: dict | None = None) -> dict:
    seller = seller or inv.seller_snapshot(db)
    return {
        "id": donation.id,
        "receipt_number": donation.receipt_number,
        "location_id": donation.location_id,
        "register_id": donation.register_id,
        "donor_name": donation.donor_name,
        "amount": inv.money(donation.amount),
        "note": donation.note,
        "payment_method": donation.payment_method,
        "card_ref": donation.card_ref,
        "proof_id": donation.proof_id,
        "status": donation.status,
        "void_reason": donation.void_reason,
        "voided_at": donation.voided_at,
        "voided_by": donation.voided_by,
        # a receipt shows who received the donation — never a VAT number / QR
        "seller": {k: seller.get(k) for k in (
            "name", "building_number", "street_name", "district", "city",
            "postal_code", "region", "country", "national_address", "cr_number")},
        "user_id": donation.user_id,
        "user_name": donation.user.full_name if donation.user else None,
        "issued_at": donation.issued_at,
        "created_at": donation.created_at,
    }
