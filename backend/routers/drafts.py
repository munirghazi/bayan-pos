"""Drafts — a sale or donation paid by bank transfer whose proof is not ready yet.

A draft is NOT a document: no number, no QR, no VAT record, no stock movement.
Its items are reserved (other sales can't take them) until it is issued — with
the proof attached, at which point the real invoice / receipt is issued and gets
its number — or cancelled. Drafts left open past the end of the Riyadh day are
cancelled automatically.

ZATCA: a simplified invoice is due at the time of supply, so a draft is only
for the case where the goods stay in the store until the transfer is confirmed.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

import invoicing as inv
import payments as pay
from capabilities import require_sales, require_donations, require_invoice_identity
from database import get_db, PosDraft, Customer
from routers.auth import get_current_user, User

router = APIRouter()
KSA = ZoneInfo("Asia/Riyadh")


class CancelIn(BaseModel):
    reason: str | None = None


class IssueIn(BaseModel):
    payments: list[pay.PaymentIn] | None = None     # sale: full tender list, now with proofs
    proof_id: int | None = None                     # donation: the transfer proof


def _today_start_utc():
    now = datetime.now(KSA)
    return datetime(now.year, now.month, now.day, tzinfo=KSA).astimezone(timezone.utc)


def expire_old(db) -> None:
    db.execute(text(
        "UPDATE pos_drafts SET status='cancelled', cancel_reason='انتهى اليوم دون إرفاق الإثبات', "
        "closed_at=now() WHERE status='open' AND created_at < :t"), {"t": _today_start_utc()})


def _get_open(db, draft_id: int) -> PosDraft:
    expire_old(db)
    d = db.query(PosDraft).filter(PosDraft.id == draft_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="المسودة غير موجودة")
    if d.status != "open":
        raise HTTPException(status_code=400, detail="المسودة ليست مفتوحة (صدرت أو أُلغيت)")
    return d


def _fmt(d: PosDraft) -> dict:
    return {
        "id": d.id, "kind": d.kind, "status": d.status, "total": inv.money(d.total),
        "customer_label": d.customer_label, "payload": d.payload,
        "location_id": d.location_id, "register_id": d.register_id,
        "user_name": d.user.full_name if d.user else None,
        "issued_ref": d.issued_ref, "cancel_reason": d.cancel_reason,
        "created_at": inv.iso_z(d.created_at), "closed_at": inv.iso_z(d.closed_at),
    }


# ---------------------------------------------------------------- sale drafts

@router.post("/sale")
def create_sale_draft(request: dict, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user),
                      _caps: dict = Depends(require_sales),
                      _inv: None = Depends(require_invoice_identity)):
    from routers.sales import SaleCreate, prepare_sale, request_payments
    req = SaleCreate(**request)
    prep = prepare_sale(db, req, user)            # validates stock incl. other drafts
    lines, _, missing = pay.validate_payments(db, request_payments(req, prep["totals"]["total"]),
                                              prep["totals"]["total"], inv.SALE_PAYMENT_METHODS, draft=True)
    if not missing:
        raise HTTPException(status_code=400, detail="لا حاجة لمسودة — أصدر الفاتورة مباشرة")
    label = None
    if req.customer_id:
        c = db.query(Customer).filter(Customer.id == req.customer_id).first()
        label = (c.name + (f" — {c.phone}" if c.phone else "")) if c else None
    d = PosDraft(kind="sale", location_id=prep["location_id"], register_id=prep["register_id"],
                 user_id=user.id, payload=req.model_dump(), total=prep["totals"]["total"],
                 customer_label=label)
    db.add(d)
    db.commit()
    db.refresh(d)
    return _fmt(d)


@router.get("/")
def list_drafts(status: str = "open", kind: str | None = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    expire_old(db)
    db.commit()
    q = db.query(PosDraft).filter(PosDraft.status == status)
    if kind:
        q = q.filter(PosDraft.kind == kind)
    return [_fmt(d) for d in q.order_by(PosDraft.created_at.desc()).limit(200).all()]


@router.post("/{draft_id}/issue")
def issue_draft(draft_id: int, body: IssueIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    d = _get_open(db, draft_id)
    if d.kind == "sale":
        from capabilities import get_tenant_caps
        from routers.sales import SaleCreate, issue_sale, format_sale
        payload = dict(d.payload)
        if body.payments:
            payload["payments"] = [p.model_dump() for p in body.payments]
        req = SaleCreate(**payload)
        def close(sale):
            d.status, d.issued_ref, d.closed_at = "issued", sale.invoice_number, inv.utcnow()
        sale = issue_sale(db, req, user, exclude_draft_id=d.id, before_commit=close)
        db.refresh(d)
        return {"draft": _fmt(d), "sale": format_sale(sale)}

    from routers.donations import DonationCreate, issue_donation, _format_donation
    payload = dict(d.payload)
    if body.proof_id:
        payload["proof_id"] = body.proof_id
    def close(don):
        d.status, d.issued_ref, d.closed_at = "issued", don.receipt_number, inv.utcnow()
    don = issue_donation(db, DonationCreate(**payload), user, before_commit=close)
    db.refresh(d)
    return {"draft": _fmt(d), "donation": _format_donation(db, don)}


@router.post("/{draft_id}/cancel")
def cancel_draft(draft_id: int, body: CancelIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    d = _get_open(db, draft_id)
    d.status, d.closed_at = "cancelled", inv.utcnow()
    d.cancel_reason = ((body.reason or "").strip() or "ألغيت يدوياً")[:200]
    db.commit()
    return _fmt(d)


# ---------------------------------------------------------------- donation drafts

@router.post("/donation")
def create_donation_draft(request: dict, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user),
                          _caps: dict = Depends(require_donations)):
    from routers.donations import DonationCreate, validate_donation
    req = DonationCreate(**request)
    if req.payment_method != "transfer" or req.proof_id:
        raise HTTPException(status_code=400, detail="المسودة للتبرع بالتحويل الذي لم يُرفق إثباته بعد")
    location_id, register_id = validate_donation(db, req, user, draft=True)
    d = PosDraft(kind="donation", location_id=location_id, register_id=register_id,
                 user_id=user.id, payload=req.model_dump(), total=inv.q2(req.amount),
                 customer_label=(req.donor_name or None))
    db.add(d)
    db.commit()
    db.refresh(d)
    return _fmt(d)
