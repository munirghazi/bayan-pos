"""Dashboard + sales / donations reports.

* days are Riyadh calendar days (UTC+3), filtered on the document's issued_at;
* sales figures come from the stored invoice snapshot (VAT never recomputed);
  credit notes in the period are reported so net sales / net VAT are visible;
* donation figures disappear entirely when the tenant's donations flag is off,
  and voided receipts are listed but excluded from totals.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

import invoicing as inv
from capabilities import get_tenant_caps, require_donations
from database import get_db, Sale, Donation, Product, Return
from routers.auth import get_current_user, User

router = APIRouter()
KSA = ZoneInfo("Asia/Riyadh")


def _day_bounds_utc(day):
    start = datetime(day.year, day.month, day.day, tzinfo=KSA)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _range_utc(start_date: str | None, end_date: str | None):
    lo = hi = None
    if start_date:
        lo = _day_bounds_utc(datetime.strptime(start_date, "%Y-%m-%d").date())[0]
    if end_date:
        hi = _day_bounds_utc(datetime.strptime(end_date, "%Y-%m-%d").date())[1]
    return lo, hi


def _f(x) -> float:
    return inv.money(x or 0)


# ===================== Dashboard =====================

@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
                  caps: dict = Depends(get_tenant_caps)):
    t0, t1 = _day_bounds_utc(datetime.now(KSA).date())

    today_sales = db.query(func.coalesce(func.sum(Sale.total), 0)).filter(
        Sale.issued_at >= t0, Sale.issued_at < t1).scalar()
    today_sales_count = db.query(func.count(Sale.id)).filter(
        Sale.issued_at >= t0, Sale.issued_at < t1).scalar()
    total_sales = db.query(func.coalesce(func.sum(Sale.total), 0)).scalar()
    total_sales_count = db.query(func.count(Sale.id)).scalar()

    low_stock = db.query(Product).filter(Product.stock <= 5, Product.is_active == True).all()  # noqa: E712
    recent_sales = db.query(Sale).order_by(Sale.issued_at.desc(), Sale.id.desc()).limit(5).all()

    out = {
        "donations_enabled": bool(caps.get("donations_enabled")),
        "today": {
            "sales_total": _f(today_sales),
            "sales_count": today_sales_count,
        },
        "all_time": {
            "sales_total": _f(total_sales),
            "sales_count": total_sales_count,
        },
        "low_stock": [{"id": p.id, "name": p.name, "stock": p.stock} for p in low_stock],
        "recent_sales": [{
            "id": s.id,
            "invoice_number": s.invoice_number,
            "total": _f(s.total),
            "payment_method": s.payment_method,
            "issued_at": inv.iso_z(s.issued_at),
            "created_at": inv.iso_z(s.issued_at),
            "user_name": s.user.full_name if s.user else None,
        } for s in recent_sales],
    }

    if caps.get("donations_enabled"):
        live = db.query(Donation).filter(Donation.status == "issued")
        today_q = live.filter(Donation.issued_at >= t0, Donation.issued_at < t1)
        out["today"]["donations_total"] = _f(today_q.with_entities(
            func.coalesce(func.sum(Donation.amount), 0)).scalar())
        out["today"]["donations_count"] = today_q.count()
        out["all_time"]["donations_total"] = _f(live.with_entities(
            func.coalesce(func.sum(Donation.amount), 0)).scalar())
        out["all_time"]["donations_count"] = live.count()
        out["recent_donations"] = [{
            "id": d.id,
            "receipt_number": d.receipt_number,
            "amount": _f(d.amount),
            "donor_name": d.donor_name,
            "issued_at": inv.iso_z(d.issued_at),
            "created_at": inv.iso_z(d.issued_at),
        } for d in live.order_by(Donation.issued_at.desc(), Donation.id.desc()).limit(5).all()]
    return out


# ===================== Sales report =====================

@router.get("/sales-report")
def get_sales_report(
    start_date: str = Query(None, description="YYYY-MM-DD (Riyadh)"),
    end_date: str = Query(None, description="YYYY-MM-DD (Riyadh)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lo, hi = _range_utc(start_date, end_date)
    q = db.query(Sale)
    rq = db.query(Return)
    if lo:
        q = q.filter(Sale.issued_at >= lo)
        rq = rq.filter(Return.issued_at >= lo)
    if hi:
        q = q.filter(Sale.issued_at < hi)
        rq = rq.filter(Return.issued_at < hi)
    # Load items / payments / customer / user in a few bulk queries instead of
    # 4 queries per invoice (stress test: report p95 8.7 s at ~500 invoices).
    from sqlalchemy.orm import selectinload
    sales = (q.options(selectinload(Sale.items), selectinload(Sale.payments),
                       selectinload(Sale.customer), selectinload(Sale.user))
             .order_by(Sale.issued_at.desc(), Sale.id.desc()).all())
    credit_notes = rq.order_by(Return.issued_at.desc(), Return.id.desc()).all()

    def tot(rows, attr):
        return sum(inv.d(getattr(r, attr) or 0) for r in rows)

    def by_method(method):     # from the tenders, so split invoices count correctly
        return sum(inv.d(p.amount or 0) for s in sales for p in s.payments if p.method == method)

    sales_list = []
    for s in sales:
        items_detail = [{
            "product_id": it.product_id,
            "product_name": it.product_name or (it.product.name if it.product else "منتج محذوف"),
            "quantity": it.quantity,
            "price": float(it.price),
            "subtotal": _f(it.line_total),
            "vat": _f(it.line_vat),
            "is_tax_exempt": it.is_tax_exempt,
        } for it in s.items]
        sales_list.append({
            "id": s.id,
            "invoice_number": s.invoice_number,
            "is_tax_invoice": s.is_tax_invoice,
            "subtotal": _f(s.subtotal),
            "vat_amount": _f(s.vat_amount),
            "total": _f(s.total),
            "payment_method": s.payment_method,
            "payments": [{"method": p.method, "amount": _f(p.amount), "card_ref": p.card_ref,
                          "proof_id": p.proof_id} for p in s.payments],
            "change_given": _f(s.change_given),
            "customer_name": s.customer.name if s.customer else None,
            "issued_at": inv.iso_z(s.issued_at),
            "created_at": inv.iso_z(s.issued_at),
            "user_name": s.user.full_name if s.user else None,
            "items_count": len(s.items),
            "items": items_detail,
            "products_summary": " | ".join(
                f"{it['product_name']} ×{it['quantity']}" for it in items_detail),
        })

    gross, gross_vat = tot(sales, "total"), tot(sales, "vat_amount")
    cn_total, cn_vat = tot(credit_notes, "total"), tot(credit_notes, "vat_amount")
    return {
        "sales": sales_list,
        "credit_notes": [{
            "id": r.id,
            "credit_note_number": r.credit_note_number,
            "original_invoice_number": r.original_invoice_number,
            "total": _f(r.total),
            "vat_amount": _f(r.vat_amount),
            "reason": r.reason,
            "refund_method": r.refund_method,
            "issued_at": inv.iso_z(r.issued_at),
        } for r in credit_notes],
        "summary": {
            "total": _f(gross),
            "count": len(sales),
            "subtotal": _f(tot(sales, "subtotal")),
            "vat_total": _f(gross_vat),
            "cash_total": _f(by_method("cash")),
            "card_total": _f(by_method("card")),
            "transfer_total": _f(by_method("transfer")),
            "mixed_count": sum(1 for s in sales if s.payment_method == "mixed"),
            "cash_refunds": _f(sum(inv.d(r.total) for r in credit_notes if r.refund_method == "cash")),
            "credit_notes_count": len(credit_notes),
            "credit_notes_total": _f(cn_total),
            "credit_notes_vat": _f(cn_vat),
            "net_total": _f(gross - cn_total),
            "net_vat": _f(gross_vat - cn_vat),
        },
    }


# ===================== Donations report =====================

@router.get("/donations-report")
def get_donations_report(
    start_date: str = Query(None, description="YYYY-MM-DD (Riyadh)"),
    end_date: str = Query(None, description="YYYY-MM-DD (Riyadh)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _caps: dict = Depends(require_donations),
):
    lo, hi = _range_utc(start_date, end_date)
    q = db.query(Donation)
    if lo:
        q = q.filter(Donation.issued_at >= lo)
    if hi:
        q = q.filter(Donation.issued_at < hi)
    donations = q.order_by(Donation.issued_at.desc(), Donation.id.desc()).all()
    live = [d for d in donations if d.status == "issued"]

    def tot(method=None):
        return _f(sum(inv.d(d.amount) for d in live if method is None or d.payment_method == method))

    return {
        "donations": [{
            "id": d.id,
            "receipt_number": d.receipt_number,
            "amount": _f(d.amount),
            "donor_name": d.donor_name,
            "note": d.note,
            "payment_method": d.payment_method,
            "card_ref": d.card_ref,
            "proof_id": d.proof_id,
            "status": d.status,
            "void_reason": d.void_reason,
            "issued_at": inv.iso_z(d.issued_at),
            "created_at": inv.iso_z(d.issued_at),
            "user_name": d.user.full_name if d.user else None,
        } for d in donations],
        "summary": {
            "total": tot(),
            "count": len(live),
            "void_count": len(donations) - len(live),
            "cash_total": tot("cash"),          # historical only — new donations can't be cash
            "card_total": tot("card"),
            "transfer_total": tot("transfer"),
        },
    }
