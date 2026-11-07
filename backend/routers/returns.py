from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db, Sale, SaleItem, Product, Return, ReturnItem
from routers.auth import get_current_user, require_admin, User
from perms import require_perm
from tenant_audit import tenant_audit
from kits import explode_to_leaves
from stock import record_movement, to_base_qty
import invoicing as inv

router = APIRouter()


# ===================== Schemas =====================

class ReturnItemIn(BaseModel):
    product_id: int
    quantity: float


class ReturnCreate(BaseModel):
    sale_id: int | None = None
    invoice_number: str | None = None     # preferred: B01-INV-000123
    items: list[ReturnItemIn]
    reason: str | None = None
    register_id: int | None = None
    refund_method: str | None = None      # cash, or a method used on the invoice


def _returned_map(db: Session, sale_id: int) -> dict[int, int]:
    """product_id -> quantity already returned for this sale."""
    rows = (
        db.query(ReturnItem.product_id, func.coalesce(func.sum(ReturnItem.quantity), 0))
        .join(Return, Return.id == ReturnItem.return_id)
        .filter(Return.sale_id == sale_id)
        .group_by(ReturnItem.product_id)
        .all()
    )
    return {pid: float(q) for pid, q in rows}


def _format_return(r: Return) -> dict:
    return {
        "id": r.id,
        "sale_id": r.sale_id,
        "credit_note_number": r.credit_note_number,
        "original_invoice_number": r.original_invoice_number,
        "is_tax_invoice": r.is_tax_invoice,
        "uuid": str(r.uuid),
        "location_id": r.location_id,
        "subtotal": inv.money(r.subtotal),
        "vat_amount": inv.money(r.vat_amount),
        "total": inv.money(r.total),
        "reason": r.reason,
        "refund_method": r.refund_method,
        "seller": r.seller or {},
        "qr_data": r.qr_data,
        "original_issued_at": r.sale.issued_at if r.sale else None,
        "customer_name": r.sale.customer.name if r.sale and r.sale.customer else None,
        "customer_phone": r.sale.customer.phone if r.sale and r.sale.customer else None,
        "issued_at": r.issued_at,
        "created_at": r.created_at,
        "items": [
            {
                "product_id": i.product_id,
                "product_name": i.product_name or (i.product.name if i.product else None),
                "quantity": i.quantity,
                "price": float(i.price),
                "vat_rate": float(i.vat_rate or 0),
                "line_total": inv.money(i.line_total),
                "line_vat": inv.money(i.line_vat),
            }
            for i in r.items
        ],
    }


def _find_sale(db: Session, sale_id: int | None, invoice_number: str | None) -> Sale:
    q = db.query(Sale)
    if invoice_number:
        sale = q.filter(Sale.invoice_number == invoice_number.strip().upper()).first()
    elif sale_id is not None:
        sale = q.filter(Sale.id == sale_id).first()
    else:
        raise HTTPException(status_code=400, detail="حدد رقم الفاتورة")
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return sale


# ===================== Routes =====================

@router.get("/invoice/{invoice_number}")
def returnable_by_number(invoice_number: str, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    sale = _find_sale(db, None, invoice_number)
    return returnable(sale.id, db, user)


@router.get("/sale/{sale_id}")
def returnable(sale_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """What can still be returned from a sale (sold - already returned)."""
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    already = _returned_map(db, sale_id)
    lines = []
    for si in db.query(SaleItem).filter(SaleItem.sale_id == sale_id).all():
        prod = db.query(Product).filter(Product.id == si.product_id).first()
        ret = already.get(si.product_id, 0)
        lines.append({
            "product_id": si.product_id,
            "product_name": si.product_name or (prod.name if prod else None),
            "price": float(si.price),
            "sold": si.quantity,
            "returned": ret,
            "remaining": si.quantity - ret,
        })
    methods = sorted({p.method for p in sale.payments} | {"cash"})
    return {"sale_id": sale_id, "invoice_number": sale.invoice_number,
            "refund_methods": methods, "payment_method": sale.payment_method,
            "customer_name": sale.customer.name if sale.customer else None,
            "issued_at": sale.issued_at, "total": inv.money(sale.total), "items": lines}


@router.get("/")
def list_returns(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Return).order_by(Return.created_at.desc()).limit(200).all()
    return [_format_return(r) for r in rows]


@router.get("/{return_id}")
def get_return(return_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    r = db.query(Return).filter(Return.id == return_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="المرتجع غير موجود")
    return _format_return(r)


@router.post("/")
def create_return(req: ReturnCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_perm("returns"))):
    if not req.items:
        raise HTTPException(status_code=400, detail="يجب تحديد صنف واحد على الأقل")
    if not (req.reason or "").strip():
        # ZATCA: a credit note must state the reason it was issued.
        raise HTTPException(status_code=400, detail="سبب الإرجاع مطلوب لإصدار الإشعار الدائن")

    sale = _find_sale(db, req.sale_id, req.invoice_number)
    # Refund: cash is always allowed, plus any method used on the invoice.
    paid_methods = {p.method for p in sale.payments}
    allowed_refund = paid_methods | {"cash"}
    refund_method = (req.refund_method or "").strip() or (
        next(iter(paid_methods)) if len(paid_methods) == 1 else None)
    if not refund_method:
        raise HTTPException(status_code=400, detail="اختر طريقة الاسترداد")
    if refund_method not in allowed_refund:
        raise HTTPException(status_code=400,
                            detail="طريقة الاسترداد يجب أن تكون نقداً أو إحدى طرق دفع الفاتورة الأصلية")

    sold = {si.product_id: si for si in
            db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()}
    already = _returned_map(db, sale.id)

    leaf_restock: dict[int, int] = {}
    validated = []
    for it in req.items:
        if it.quantity <= 0:
            raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
        si = sold.get(it.product_id)
        if not si:
            raise HTTPException(status_code=400, detail="أحد الأصناف غير موجود في الفاتورة الأصلية")
        prod = db.query(Product).filter(Product.id == it.product_id).first()
        if prod and prod.is_kit and float(it.quantity) != int(it.quantity):
            raise HTTPException(status_code=400, detail=f"كمية '{prod.name}' يجب أن تكون عدداً صحيحاً")
        remaining = si.quantity - already.get(it.product_id, 0)
        if it.quantity > remaining:
            prod = db.query(Product).filter(Product.id == it.product_id).first()
            name = prod.name if prod else it.product_id
            raise HTTPException(status_code=400,
                                detail=f"الكمية المرتجعة من '{name}' تتجاوز المتبقي ({remaining})")
        product = db.query(Product).filter(Product.id == it.product_id).first()
        # Reverse the sale's stock math in BASE units (convert from the sold unit).
        base_qty = it.quantity if product.is_kit else to_base_qty(db, product, it.quantity, si.uom_id)
        explode_to_leaves(db, product, base_qty, leaf_restock)
        validated.append({"product_id": it.product_id, "quantity": it.quantity,
                          "price": si.price, "vat_rate": inv.d(si.vat_rate or 0),
                          "name": si.product_name or (product.name if product else None)})

    # ---- issue the credit note: in the ORIGINAL invoice's branch, at the ORIGINAL VAT rates
    lines, total, vat = [], inv.d(0), inv.d(0)
    for v in validated:
        lt = inv.q2(inv.d(v["price"]) * inv.d(v["quantity"]))
        r = v["vat_rate"]
        lv = inv.q2(lt - lt / (1 + r / 100)) if r else inv.d(0)
        lines.append({**v, "line_total": lt, "line_vat": lv})
        total += lt
        vat += lv
    total, vat = inv.q2(total), inv.q2(vat)
    seller = dict(sale.seller or {})
    if not seller:
        seller = inv.seller_snapshot(db)
    alloc = inv.allocate(db, sale.location_id, inv.DOC_CREDIT_NOTE)
    issued_at = inv.utcnow()
    uid = inv.new_uuid()
    doc_hash = inv.document_hash({
        "type": inv.DOC_CREDIT_NOTE, "number": alloc.number, "uuid": uid, "icv": alloc.seq,
        "pih": alloc.previous_hash, "issued_at": issued_at, "ref": sale.invoice_number,
        "seller_vat": seller.get("vat_number"), "total": total, "vat": vat,
        "lines": [{"name": ln["name"], "qty": inv.d(ln["quantity"]), "price": inv.d(ln["price"]),
                   "vat": ln["line_vat"]} for ln in lines],
    })
    qr = (inv.zatca_qr(seller.get("name"), seller.get("vat_number"), issued_at, total, vat)
          if sale.is_tax_invoice else None)

    ret = Return(
        sale_id=sale.id, user_id=user.id, register_id=req.register_id,
        location_id=sale.location_id,
        credit_note_number=alloc.number, credit_note_seq=alloc.seq,
        original_invoice_number=sale.invoice_number, is_tax_invoice=sale.is_tax_invoice,
        uuid=uid, previous_hash=alloc.previous_hash, invoice_hash=doc_hash, issued_at=issued_at,
        subtotal=total - vat, vat_amount=vat, total=total, seller=seller, qr_data=qr,
        reason=(req.reason or "").strip() or None,
        refund_method=refund_method,
    )
    db.add(ret)
    db.flush()

    for ln in lines:
        db.add(ReturnItem(return_id=ret.id, product_id=ln["product_id"], product_name=ln["name"],
                          quantity=ln["quantity"], price=ln["price"], vat_rate=ln["vat_rate"],
                          line_total=ln["line_total"], line_vat=ln["line_vat"]))
    inv.commit_allocation(db, alloc, doc_hash)

    for leaf_id, qty in leaf_restock.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        if leaf:
            leaf.stock = round(float(leaf.stock or 0) + float(qty), 3)
            record_movement(db, leaf, float(qty), "in", ref_type="return",
                            ref_id=ret.id, user_id=user.id)

    db.commit()
    db.refresh(ret)
    tenant_audit(db, user, "refund", target=getattr(ret, 'id', None))
    return _format_return(ret)
