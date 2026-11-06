"""Sales = simplified tax invoices (B2C).

An invoice is issued in one transaction: items validated against stock (minus
what open drafts have reserved), VAT + seller snapshot, per-branch number and
hash chain, QR, tenders (split payment), stock movements. Nothing about an
issued invoice can change afterwards (DB triggers).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import idempotency
import invoicing as inv
import payments as pay
from capabilities import require_sales, require_invoice_identity
from database import (get_db, Sale, SaleItem, SalePayment, Product, Customer, ConsignmentItem,
                      ConsignmentLedger, Return, Location, PosDraft)
from kits import explode_to_leaves
from routers.auth import get_current_user, User
from stock import record_movement, to_base_qty
from perms import require_perm

router = APIRouter()


# ===================== Schemas =====================

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: float
    uom_id: int | None = None   # unit sold in; defaults to the product's sales unit
    consignment_item_id: int | None = None


class SaleCreate(BaseModel):
    items: list[SaleItemCreate]
    # split payment: one entry per tender. (Legacy single-method fields below
    # are still accepted: they become one tender for the full total.)
    payments: list[pay.PaymentIn] | None = None
    payment_method: str | None = None
    card_ref: str | None = None
    register_id: int | None = None
    customer_id: int | None = None


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str | None = None
    quantity: float
    uom_id: int | None = None
    uom_name: str | None = None
    price: float
    is_tax_exempt: bool = False
    vat_rate: float = 0
    line_total: float = 0
    line_vat: float = 0


class PaymentResponse(BaseModel):
    method: str
    amount: float
    tendered: float | None = None
    card_ref: str | None = None
    proof_id: int | None = None


class SaleResponse(BaseModel):
    id: int
    invoice_number: str
    invoice_type: str
    is_tax_invoice: bool
    uuid: str
    location_id: int
    location_code: str | None = None
    user_id: int
    user_name: str | None = None
    subtotal: float
    vat_amount: float
    exempt_amount: float = 0
    total: float
    change_given: float = 0
    payment_method: str
    card_ref: str | None = None
    payments: list[PaymentResponse] = []
    register_id: int | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    seller: dict
    qr_data: str | None = None
    items: list[SaleItemResponse]
    issued_at: datetime
    created_at: datetime


# ===================== Stock reserved by open drafts =====================

def _demand_for_items(db, items) -> tuple[dict[int, float], dict[int, float]]:
    """(leaf product demand in base units, consignment-lot demand) for item dicts."""
    leaf, lots = {}, {}
    for it in items:
        it = it if isinstance(it, dict) else it.model_dump()
        product = db.query(Product).filter(Product.id == it["product_id"]).first()
        if not product:
            continue
        if it.get("consignment_item_id"):
            lots[it["consignment_item_id"]] = lots.get(it["consignment_item_id"], 0) + float(it["quantity"])
            continue
        uom_id = it.get("uom_id") or product.sales_uom_id or product.uom_id
        base = it["quantity"] if product.is_kit else to_base_qty(db, product, it["quantity"], uom_id)
        explode_to_leaves(db, product, base, leaf)
    return leaf, lots


def reserved_by_drafts(db, exclude_draft_id: int | None = None):
    import routers.drafts as drafts
    drafts.expire_old(db)
    q = db.query(PosDraft).filter(PosDraft.kind == "sale", PosDraft.status == "open")
    if exclude_draft_id:
        q = q.filter(PosDraft.id != exclude_draft_id)
    leaf, lots = {}, {}
    for dr in q.all():
        l2, c2 = _demand_for_items(db, dr.payload.get("items", []))
        for k, v in l2.items():
            leaf[k] = leaf.get(k, 0) + v
        for k, v in c2.items():
            lots[k] = lots.get(k, 0) + v
    return leaf, lots


# ===================== Issuing =====================

def prepare_sale(db, request: SaleCreate, user, exclude_draft_id: int | None = None) -> dict:
    """Validate items/stock/customer/branch and price the invoice. No writes."""
    if not request.items:
        raise HTTPException(status_code=400, detail="يجب إضافة منتج واحد على الأقل")
    location_id, register_id = inv.resolve_location(db, request.register_id, user)
    if request.customer_id is not None:
        if not db.query(Customer).filter(Customer.id == request.customer_id).first():
            raise HTTPException(status_code=400, detail="العميل غير موجود")

    reserved_leaf, reserved_lots = reserved_by_drafts(db, exclude_draft_id)
    sale_items = []
    leaf_demand: dict[int, float] = {}
    for item in request.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"المنتج رقم {item.product_id} غير موجود")
        if product.is_kit and float(item.quantity) != int(item.quantity):
            raise HTTPException(status_code=400, detail=f"كمية '{product.name}' يجب أن تكون عدداً صحيحاً")
        sell_uom_id = item.uom_id or product.sales_uom_id or product.uom_id

        if item.consignment_item_id:
            ci = db.query(ConsignmentItem).filter(ConsignmentItem.id == item.consignment_item_id).first()
            if not ci or ci.product_id != product.id:
                raise HTTPException(status_code=400, detail="صنف الأمانة غير صالح")
            if getattr(ci, "status", "active") != "active":
                raise HTTPException(status_code=400, detail="صنف الأمانة غير متاح للبيع")
            avail = round(float(ci.qty_remaining or 0) - reserved_lots.get(ci.id, 0), 3)
            if avail < round(float(item.quantity), 3):
                raise HTTPException(status_code=400,
                                    detail=f"الكمية المتاحة من الأمانة غير كافية. المتاح: {max(avail, 0):g}")
            sale_items.append({"product": product, "quantity": item.quantity, "uom_id": sell_uom_id,
                               "price": ci.unit_price, "is_tax_exempt": product.is_tax_exempt,
                               "consignment_item": ci})
            continue

        base_qty = item.quantity if product.is_kit else to_base_qty(db, product, item.quantity, sell_uom_id)
        sale_items.append({"product": product, "quantity": item.quantity, "uom_id": sell_uom_id,
                           "price": product.price, "is_tax_exempt": product.is_tax_exempt,
                           "consignment_item": None})
        explode_to_leaves(db, product, base_qty, leaf_demand)

    for leaf_id, need in leaf_demand.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        if leaf is None:
            raise HTTPException(status_code=400, detail=f"أحد مكوّنات المنتج (رقم {leaf_id}) غير موجود")
        avail = round(float(leaf.stock or 0) - reserved_leaf.get(leaf_id, 0), 3)
        if avail < round(float(need), 3):
            held = reserved_leaf.get(leaf_id, 0)
            extra = f" (محجوز في مسودات: {held:g})" if held else ""
            raise HTTPException(status_code=400,
                                detail=f"الكمية المطلوبة من '{leaf.name}' غير متوفرة. المتاح: {max(avail, 0):g}{extra}")

    from database import Uom
    seller = inv.seller_snapshot(db)
    for it in sale_items:
        uom = db.query(Uom).filter(Uom.id == it["uom_id"]).first() if it["uom_id"] else None
        it["uom_name"] = uom.name if uom else (getattr(it["product"], "unit", None) or None)
    priced, totals = inv.price_lines(sale_items, seller)
    return {"location_id": location_id, "register_id": register_id, "seller": seller,
            "priced": priced, "totals": totals, "leaf_demand": leaf_demand}


def request_payments(request: SaleCreate, total: Decimal) -> list[pay.PaymentIn]:
    if request.payments:
        return request.payments
    if not request.payment_method:
        raise HTTPException(status_code=400, detail="أضف طريقة دفع واحدة على الأقل")
    return [pay.PaymentIn(method=request.payment_method, amount=float(total), card_ref=request.card_ref)]


def issue_sale(db, request: SaleCreate, user, exclude_draft_id: int | None = None,
               before_commit=None) -> Sale:
    """Issue the invoice and commit. Raises HTTPException on any rule violation."""
    prep = prepare_sale(db, request, user, exclude_draft_id)
    totals, seller, priced = prep["totals"], prep["seller"], prep["priced"]
    lines, change, _ = pay.validate_payments(db, request_payments(request, totals["total"]),
                                             totals["total"], inv.SALE_PAYMENT_METHODS)

    alloc = inv.allocate(db, prep["location_id"], inv.DOC_INVOICE)
    issued_at = inv.utcnow()
    uid = inv.new_uuid()
    doc_hash = inv.document_hash({
        "type": inv.DOC_INVOICE, "number": alloc.number, "uuid": uid, "icv": alloc.seq,
        "pih": alloc.previous_hash, "issued_at": issued_at, "seller_vat": seller["vat_number"],
        "total": totals["total"], "vat": totals["vat_amount"],
        "lines": [{"name": ln["product"].name, "qty": inv.d(ln["quantity"]),
                   "price": inv.d(ln["price"]), "vat": ln["line_vat"]} for ln in priced],
        "payments": [{"m": l["method"], "a": l["amount"]} for l in lines],
    })
    qr = (inv.zatca_qr(seller["name"], seller["vat_number"], issued_at,
                       totals["total"], totals["vat_amount"])
          if seller["vat_registered"] else None)
    first_card = next((l["card_ref"] for l in lines if l["method"] == "card"), None)

    sale = Sale(
        user_id=user.id, register_id=prep["register_id"], location_id=prep["location_id"],
        customer_id=request.customer_id,
        invoice_number=alloc.number, invoice_seq=alloc.seq, invoice_type="simplified",
        is_tax_invoice=seller["vat_registered"], uuid=uid,
        previous_hash=alloc.previous_hash, invoice_hash=doc_hash, issued_at=issued_at,
        subtotal=totals["subtotal"], vat_amount=totals["vat_amount"],
        exempt_amount=totals["exempt_amount"], total=totals["total"],
        seller=seller, qr_data=qr,
        payment_method=pay.summary_method(lines), card_ref=first_card, change_given=change,
    )
    db.add(sale)
    db.flush()

    for l in lines:
        db.add(SalePayment(sale_id=sale.id, method=l["method"], amount=l["amount"],
                           tendered=l["tendered"], card_ref=l["card_ref"], proof_id=l["proof_id"]))
        pay.mark_proof_used(db, l["proof_id"], alloc.number)

    for item_data in priced:
        ci = item_data.get("consignment_item")
        db.add(SaleItem(
            sale_id=sale.id, product_id=item_data["product"].id,
            product_name=item_data["product"].name, quantity=item_data["quantity"],
            uom_id=item_data["uom_id"], uom_name=item_data["uom_name"], price=item_data["price"],
            is_tax_exempt=item_data["is_tax_exempt"], vat_rate=item_data["vat_rate"],
            line_total=item_data["line_total"], line_vat=item_data["line_vat"],
            consignment_item_id=(ci.id if ci else None),
        ))
        if ci:
            ci.qty_remaining = round(float(ci.qty_remaining) - float(item_data["quantity"]), 3)
            subtotal = float(item_data["price"]) * float(item_data["quantity"])
            shop_share = subtotal * (float(ci.commission_percent or 0) / 100.0)
            db.add(ConsignmentLedger(
                consignor_id=ci.consignor_id, entry_type="accrual", sale_id=sale.id,
                consignment_item_id=ci.id, amount=round(subtotal - shop_share, 2),
                note=f"بيع {item_data['quantity']:g} × {item_data['product'].name}"))
    inv.commit_allocation(db, alloc, doc_hash)

    for leaf_id, need in prep["leaf_demand"].items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        leaf.stock = round(float(leaf.stock or 0) - float(need), 3)
        record_movement(db, leaf, -float(need), "out", ref_type="sale", ref_id=sale.id, user_id=user.id)

    if before_commit:
        before_commit(sale)        # e.g. close the draft in the SAME transaction
    db.commit()
    db.refresh(sale)
    return sale


# ===================== Routes =====================

@router.post("/", response_model=SaleResponse, dependencies=[Depends(require_perm("sell"))])
def create_sale(request: SaleCreate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user),
                _caps: dict = Depends(require_sales),
                _inv: None = Depends(require_invoice_identity),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    prior = idempotency.replay(db, idempotency_key, "sales")
    if prior is not None:
        return JSONResponse(content=prior)
    sale = issue_sale(db, request, current_user)
    resp = format_sale(sale)
    idempotency.store(db, idempotency_key, "sales", resp)
    return resp


@router.get("/", response_model=list[SaleResponse])
def get_sales(skip: int = 0, limit: int = 50, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    sales = db.query(Sale).order_by(Sale.issued_at.desc(), Sale.id.desc()).offset(skip).limit(limit).all()
    return [format_sale(s) for s in sales]


@router.get("/search")
def search_sales(
    q: str | None = Query(None, description="رقم الفاتورة (كامل أو جزء) أو رمز العملية"),
    date_from: str | None = Query(None, description="YYYY-MM-DD (Riyadh)"),
    date_to: str | None = Query(None, description="YYYY-MM-DD (Riyadh)"),
    customer: str | None = Query(None, description="اسم العميل أو جواله"),
    amount_min: float | None = None,
    amount_max: float | None = None,
    method: str | None = None,
    location_id: int | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invoice finder (used by Returns). Newest first."""
    from routers.reports import _range_utc
    query = db.query(Sale).outerjoin(Customer, Customer.id == Sale.customer_id)
    if q:
        term = f"%{q.strip()}%"
        refs = db.query(SalePayment.sale_id).filter(SalePayment.card_ref.ilike(term))
        query = query.filter(or_(Sale.invoice_number.ilike(term), Sale.id.in_(refs)))
    lo, hi = _range_utc(date_from, date_to)
    if lo:
        query = query.filter(Sale.issued_at >= lo)
    if hi:
        query = query.filter(Sale.issued_at < hi)
    if customer:
        term = f"%{customer.strip()}%"
        digits = "".join(ch for ch in customer if ch.isdigit()).lstrip("0")
        conds = [Customer.name.ilike(term)]
        if digits:
            conds.append(Customer.phone.ilike(f"%{digits}%"))
        query = query.filter(or_(*conds))
    if amount_min is not None:
        query = query.filter(Sale.total >= amount_min)
    if amount_max is not None:
        query = query.filter(Sale.total <= amount_max)
    if method:
        query = query.filter(Sale.id.in_(db.query(SalePayment.sale_id).filter(SalePayment.method == method)))
    if location_id:
        query = query.filter(Sale.location_id == location_id)

    total_count = query.count()
    from sqlalchemy.orm import selectinload
    rows = (query.options(selectinload(Sale.payments), selectinload(Sale.customer))
            .order_by(Sale.issued_at.desc(), Sale.id.desc()).offset(offset).limit(limit).all())
    returned = dict(db.query(Return.sale_id, func.coalesce(func.sum(Return.total), 0))
                      .filter(Return.sale_id.in_([s.id for s in rows] or [0]))
                      .group_by(Return.sale_id).all())
    return {
        "count": total_count,
        "rows": [{
            "id": s.id,
            "invoice_number": s.invoice_number,
            "issued_at": inv.iso_z(s.issued_at),
            "total": inv.money(s.total),
            "returned_total": inv.money(returned.get(s.id, 0)),
            "payment_method": s.payment_method,
            "methods": sorted({p.method for p in s.payments}),
            "customer_name": s.customer.name if s.customer else None,
            "customer_phone": s.customer.phone if s.customer else None,
            "location_code": s.location.code if s.location else None,
            "items_count": len(s.items),
        } for s in rows],
    }


@router.get("/by-number/{invoice_number}", response_model=SaleResponse)
def get_sale_by_number(invoice_number: str, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    sale = db.query(Sale).filter(Sale.invoice_number == invoice_number.strip().upper()).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return format_sale(sale)


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return format_sale(sale)


def _check_payment(db, method: str, card_ref: str | None, allowed: set[str]) -> None:
    """Single-tender check (kept for donations)."""
    enabled, _ = pay.tenant_payment_settings(db)
    if method not in allowed:
        raise HTTPException(status_code=400, detail="طريقة الدفع غير مسموحة لهذه العملية")
    if method not in enabled:
        raise HTTPException(status_code=400, detail="طريقة الدفع غير مفعّلة في الإعدادات")
    if method == "card" and not (card_ref or "").strip():
        raise HTTPException(status_code=400, detail="الرجاء إدخال رمز العملية للدفع بالشبكة")


def format_sale(sale: Sale) -> dict:
    return {
        "id": sale.id,
        "invoice_number": sale.invoice_number,
        "invoice_type": sale.invoice_type,
        "is_tax_invoice": sale.is_tax_invoice,
        "uuid": str(sale.uuid),
        "location_id": sale.location_id,
        "location_code": sale.location.code if sale.location else None,
        "user_id": sale.user_id,
        "user_name": sale.user.full_name if sale.user else None,
        "subtotal": inv.money(sale.subtotal),
        "vat_amount": inv.money(sale.vat_amount),
        "exempt_amount": inv.money(sale.exempt_amount),
        "total": inv.money(sale.total),
        "change_given": inv.money(sale.change_given or 0),
        "payment_method": sale.payment_method,
        "card_ref": sale.card_ref,
        "payments": [pay.payment_dict(p) for p in sale.payments],
        "register_id": sale.register_id,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer.name if getattr(sale, "customer", None) else None,
        "customer_phone": sale.customer.phone if getattr(sale, "customer", None) else None,
        "seller": sale.seller or {},
        "qr_data": sale.qr_data,
        "issued_at": sale.issued_at,
        "created_at": sale.created_at,
        "items": [{
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product_name or (item.product.name if item.product else None),
            "quantity": item.quantity,
            "uom_id": item.uom_id,
            "uom_name": item.uom_name,
            "price": float(item.price),
            "is_tax_exempt": item.is_tax_exempt,
            "vat_rate": float(item.vat_rate or 0),
            "line_total": inv.money(item.line_total),
            "line_vat": inv.money(item.line_vat),
        } for item in sale.items],
    }


_format_sale = format_sale   # backwards-compatible name
