from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
import idempotency
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Sale, SaleItem, Product, Customer, ConsignmentItem, ConsignmentLedger
from routers.auth import get_current_user, User
from capabilities import require_sales, require_invoice_identity
from kits import explode_to_leaves
from stock import record_movement, to_base_qty
from datetime import datetime
import invoicing as inv

router = APIRouter()


# ===================== Schemas =====================

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: float
    uom_id: int | None = None   # unit sold in; defaults to the product's sales unit
    consignment_item_id: int | None = None


class SaleCreate(BaseModel):
    items: list[SaleItemCreate]
    payment_method: str  # cash / card / transfer
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
    payment_method: str
    card_ref: str | None = None
    register_id: int | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    seller: dict
    qr_data: str | None = None
    items: list[SaleItemResponse]
    issued_at: datetime
    created_at: datetime


# ===================== Routes =====================

@router.post("/", response_model=SaleResponse)
def create_sale(request: SaleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), _caps: dict = Depends(require_sales),
                _inv: None = Depends(require_invoice_identity),
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    prior = idempotency.replay(db, idempotency_key, "sales")
    if prior is not None:
        return JSONResponse(content=prior)
    if not request.items:
        raise HTTPException(status_code=400, detail="يجب إضافة منتج واحد على الأقل")

    _check_payment(db, request.payment_method, request.card_ref, inv.SALE_PAYMENT_METHODS)
    # Every invoice belongs to a branch (its numbering series).
    location_id, register_id = inv.resolve_location(db, request.register_id, current_user)

    if request.customer_id is not None:
        if not db.query(Customer).filter(Customer.id == request.customer_id).first():
            raise HTTPException(status_code=400, detail="العميل غير موجود")

    sale_items = []
    leaf_demand: dict[int, float] = {}   # leaf product id -> total units this sale needs

    for item in request.items:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"المنتج رقم {item.product_id} غير موجود")
        if product.is_kit and float(item.quantity) != int(item.quantity):
            raise HTTPException(status_code=400, detail=f"كمية '{product.name}' يجب أن تكون عدداً صحيحاً")

        # Option B: price is per SELLING unit; stock deducts in BASE units.
        sell_uom_id = item.uom_id or product.sales_uom_id or product.uom_id

        # --- consigned lot: sell from separated consigned stock, accrue to consignor ---
        if getattr(item, "consignment_item_id", None):
            ci = db.query(ConsignmentItem).filter(
                ConsignmentItem.id == item.consignment_item_id).first()
            if not ci or ci.product_id != product.id:
                raise HTTPException(status_code=400, detail="صنف الأمانة غير صالح")
            if getattr(ci, "status", "active") != "active":
                raise HTTPException(status_code=400, detail="صنف الأمانة غير متاح للبيع")
            if round(float(ci.qty_remaining or 0), 3) < round(float(item.quantity), 3):
                raise HTTPException(status_code=400,
                    detail=f"الكمية المتاحة من الأمانة غير كافية. المتاح: {round(float(ci.qty_remaining or 0),3):g}")
            line_price = ci.unit_price
            sale_items.append({
                "product": product, "quantity": item.quantity, "uom_id": sell_uom_id,
                "price": line_price, "is_tax_exempt": product.is_tax_exempt,
                "consignment_item": ci,
            })
            continue   # do NOT touch owned stock

        base_qty = item.quantity if product.is_kit else to_base_qty(db, product, item.quantity, sell_uom_id)

        sale_items.append({
            "product": product,
            "quantity": item.quantity,        # in the selling unit
            "uom_id": sell_uom_id,
            "price": product.price,           # per selling unit
            "is_tax_exempt": product.is_tax_exempt,
            "consignment_item": None,
        })
        # Deduct stock in base units (1 شرنك -> 27 حبة).
        explode_to_leaves(db, product, base_qty, leaf_demand)

    # Validate leaf stock across the WHOLE sale (kits + direct lines combined).
    for leaf_id, need in leaf_demand.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        if leaf is None:
            raise HTTPException(status_code=400, detail=f"أحد مكوّنات المنتج (رقم {leaf_id}) غير موجود")
        if round(float(leaf.stock or 0), 3) < round(float(need), 3):
            avail = round(float(leaf.stock or 0), 3)
            raise HTTPException(status_code=400, detail=f"الكمية المطلوبة من '{leaf.name}' غير متوفرة. المتاح: {avail:g}")

    # ---- issue the invoice: VAT + seller snapshot, number, hash chain, QR
    from database import Uom
    seller = inv.seller_snapshot(db)
    for it in sale_items:
        uom = db.query(Uom).filter(Uom.id == it["uom_id"]).first() if it["uom_id"] else None
        it["uom_name"] = uom.name if uom else None
    priced, totals = inv.price_lines(sale_items, seller)
    alloc = inv.allocate(db, location_id, inv.DOC_INVOICE)
    issued_at = inv.utcnow()
    uid = inv.new_uuid()
    doc_hash = inv.document_hash({
        "type": inv.DOC_INVOICE, "number": alloc.number, "uuid": uid, "icv": alloc.seq,
        "pih": alloc.previous_hash, "issued_at": issued_at, "seller_vat": seller["vat_number"],
        "total": totals["total"], "vat": totals["vat_amount"],
        "lines": [{"name": ln["product"].name, "qty": inv.d(ln["quantity"]),
                   "price": inv.d(ln["price"]), "vat": ln["line_vat"]} for ln in priced],
    })
    qr = (inv.zatca_qr(seller["name"], seller["vat_number"], issued_at,
                       totals["total"], totals["vat_amount"])
          if seller["vat_registered"] else None)

    sale = Sale(
        user_id=current_user.id,
        register_id=register_id,
        location_id=location_id,
        customer_id=request.customer_id,
        invoice_number=alloc.number,
        invoice_seq=alloc.seq,
        invoice_type="simplified",
        is_tax_invoice=seller["vat_registered"],
        uuid=uid,
        previous_hash=alloc.previous_hash,
        invoice_hash=doc_hash,
        issued_at=issued_at,
        subtotal=totals["subtotal"],
        vat_amount=totals["vat_amount"],
        exempt_amount=totals["exempt_amount"],
        total=totals["total"],
        seller=seller,
        qr_data=qr,
        payment_method=request.payment_method,
        card_ref=(request.card_ref or "").strip() or None,
    )
    db.add(sale)
    db.flush()

    # Sale lines record the sold product (the kit itself, at its fixed price).
    for item_data in priced:
        ci = item_data.get("consignment_item")
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item_data["product"].id,
            product_name=item_data["product"].name,
            quantity=item_data["quantity"],
            uom_id=item_data["uom_id"],
            uom_name=item_data["uom_name"],
            price=item_data["price"],
            is_tax_exempt=item_data["is_tax_exempt"],
            vat_rate=item_data["vat_rate"],
            line_total=item_data["line_total"],
            line_vat=item_data["line_vat"],
            consignment_item_id=(ci.id if ci else None),
        ))
        # consigned lot: decrement remaining + accrue consignor share
        if ci:
            ci.qty_remaining = round(float(ci.qty_remaining) - float(item_data["quantity"]), 3)
            subtotal = float(item_data["price"]) * float(item_data["quantity"])
            shop_share = subtotal * (float(ci.commission_percent or 0) / 100.0)
            consignor_share = round(subtotal - shop_share, 2)
            db.add(ConsignmentLedger(
                consignor_id=ci.consignor_id, entry_type="accrual",
                sale_id=sale.id, consignment_item_id=ci.id, amount=consignor_share,
                note=f"بيع {item_data['quantity']:g} × {item_data['product'].name}"))
    inv.commit_allocation(db, alloc, doc_hash)

    # Deduct stock from leaf products only.
    for leaf_id, need in leaf_demand.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        leaf.stock = round(float(leaf.stock or 0) - float(need), 3)
        record_movement(db, leaf, -float(need), "out", ref_type="sale",
                        ref_id=sale.id, user_id=current_user.id)

    db.commit()
    db.refresh(sale)

    _resp = _format_sale(sale)
    idempotency.store(db, idempotency_key, "sales", _resp)
    return _resp


@router.get("/", response_model=list[SaleResponse])
def get_sales(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sales = db.query(Sale).order_by(Sale.created_at.desc()).offset(skip).limit(limit).all()
    return [_format_sale(s) for s in sales]


@router.get("/by-number/{invoice_number}", response_model=SaleResponse)
def get_sale_by_number(invoice_number: str, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    sale = db.query(Sale).filter(Sale.invoice_number == invoice_number.strip().upper()).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return _format_sale(sale)


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return _format_sale(sale)


def _check_payment(db, method: str, card_ref: str | None, allowed: set[str]) -> None:
    """Method must be valid for this document type AND enabled for the tenant."""
    from database import TenantSettings
    st = db.query(TenantSettings).first()
    enabled = {m.strip() for m in ((st.payment_methods if st else None) or "cash,card,transfer").split(",")}
    if method not in allowed:
        raise HTTPException(status_code=400, detail="طريقة الدفع غير مسموحة لهذه العملية")
    if method not in enabled:
        raise HTTPException(status_code=400, detail="طريقة الدفع غير مفعّلة في الإعدادات")
    if method == "card" and not (card_ref or "").strip():
        raise HTTPException(status_code=400, detail="الرجاء إدخال رمز العملية للدفع بالشبكة")


def _format_sale(sale: Sale) -> dict:
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
        "payment_method": sale.payment_method,
        "card_ref": sale.card_ref,
        "register_id": sale.register_id,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer.name if getattr(sale, "customer", None) else None,
        "seller": sale.seller or {},
        "qr_data": sale.qr_data,
        "issued_at": sale.issued_at,
        "created_at": sale.created_at,
        "items": [
            {
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
            }
            for item in sale.items
        ]
    }
