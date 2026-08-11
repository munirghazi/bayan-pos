from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Sale, SaleItem, Product, Register, Customer
from routers.auth import get_current_user, User
from kits import explode_to_leaves
from datetime import datetime

router = APIRouter()


# ===================== Schemas =====================

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: float


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
    price: float
    is_tax_exempt: bool = False

    class Config:
        from_attributes = True


class SaleResponse(BaseModel):
    id: int
    user_id: int
    user_name: str | None = None
    total: float
    payment_method: str
    card_ref: str | None = None
    register_id: int | None = None
    customer_id: int | None = None
    customer_name: str | None = None
    items: list[SaleItemResponse]
    created_at: datetime

    class Config:
        from_attributes = True


# ===================== Routes =====================

@router.post("/", response_model=SaleResponse)
def create_sale(request: SaleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not request.items:
        raise HTTPException(status_code=400, detail="يجب إضافة منتج واحد على الأقل")

    if request.register_id is not None:
        reg = db.query(Register).filter(Register.id == request.register_id).first()
        if not reg:
            raise HTTPException(status_code=400, detail="الصندوق غير موجود")
        # A branch-assigned user may only sell on a register in their own branch.
        if current_user.location_id is not None and reg.location_id != current_user.location_id:
            raise HTTPException(status_code=403, detail="لا يمكنك البيع على صندوق خارج فرعك")

    if request.customer_id is not None:
        if not db.query(Customer).filter(Customer.id == request.customer_id).first():
            raise HTTPException(status_code=400, detail="العميل غير موجود")

    total = 0.0
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

        # Kits use their fixed price; stock is deducted from leaf components.
        item_total = product.price * item.quantity
        total += item_total
        sale_items.append({
            "product": product,
            "quantity": item.quantity,
            "price": product.price,
            "is_tax_exempt": product.is_tax_exempt,
        })
        # Explode kits down to leaf products; a plain product maps to itself.
        explode_to_leaves(db, product, item.quantity, leaf_demand)

    # Validate leaf stock across the WHOLE sale (kits + direct lines combined).
    for leaf_id, need in leaf_demand.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        if leaf is None:
            raise HTTPException(status_code=400, detail=f"أحد مكوّنات المنتج (رقم {leaf_id}) غير موجود")
        if round(float(leaf.stock or 0), 3) < round(float(need), 3):
            avail = round(float(leaf.stock or 0), 3)
            raise HTTPException(status_code=400, detail=f"الكمية المطلوبة من '{leaf.name}' غير متوفرة. المتاح: {avail:g}")

    # Create sale
    sale = Sale(
        user_id=current_user.id,
        register_id=request.register_id,
        customer_id=request.customer_id,
        total=round(total, 2),
        payment_method=request.payment_method,
        card_ref=request.card_ref,
    )
    db.add(sale)
    db.flush()

    # Sale lines record the sold product (the kit itself, at its fixed price).
    for item_data in sale_items:
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=item_data["product"].id,
            quantity=item_data["quantity"],
            price=item_data["price"],
            is_tax_exempt=item_data["is_tax_exempt"],
        ))

    # Deduct stock from leaf products only.
    for leaf_id, need in leaf_demand.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        leaf.stock = round(float(leaf.stock or 0) - float(need), 3)

    db.commit()
    db.refresh(sale)

    return _format_sale(sale)


@router.get("/", response_model=list[SaleResponse])
def get_sales(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sales = db.query(Sale).order_by(Sale.created_at.desc()).offset(skip).limit(limit).all()
    return [_format_sale(s) for s in sales]


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sale = db.query(Sale).filter(Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")
    return _format_sale(sale)


def _format_sale(sale: Sale) -> dict:
    return {
        "id": sale.id,
        "user_id": sale.user_id,
        "user_name": sale.user.full_name if sale.user else None,
        "total": sale.total,
        "payment_method": sale.payment_method,
        "card_ref": sale.card_ref,
        "register_id": sale.register_id,
        "customer_id": sale.customer_id,
        "customer_name": sale.customer.name if getattr(sale, "customer", None) else None,
        "created_at": sale.created_at,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product.name if item.product else None,
                "quantity": item.quantity,
                "price": item.price,
                "is_tax_exempt": item.is_tax_exempt,
            }
            for item in sale.items
        ]
    }
