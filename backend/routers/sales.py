from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Sale, SaleItem, Product
from routers.auth import get_current_user, User
from datetime import datetime

router = APIRouter()


# ===================== Schemas =====================

class SaleItemCreate(BaseModel):
    product_id: int
    quantity: int


class SaleCreate(BaseModel):
    items: list[SaleItemCreate]
    payment_method: str  # cash / card / transfer
    card_ref: str | None = None


class SaleItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str | None = None
    quantity: int
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
    items: list[SaleItemResponse]
    created_at: datetime

    class Config:
        from_attributes = True


# ===================== Routes =====================

@router.post("/", response_model=SaleResponse)
def create_sale(request: SaleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not request.items:
        raise HTTPException(status_code=400, detail="يجب إضافة منتج واحد على الأقل")

    total = 0.0
    sale_items = []

    for item in request.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"المنتج رقم {item.product_id} غير موجود")
        if product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"الكمية المطلوبة من '{product.name}' غير متوفرة. المتاح: {product.stock}")

        item_total = product.price * item.quantity
        total += item_total
        sale_items.append({
            "product": product,
            "quantity": item.quantity,
            "price": product.price,
            "is_tax_exempt": product.is_tax_exempt,
        })

    # Create sale
    sale = Sale(
        user_id=current_user.id,
        total=round(total, 2),
        payment_method=request.payment_method,
        card_ref=request.card_ref,
    )
    db.add(sale)
    db.flush()

    # Create sale items and update stock
    for item_data in sale_items:
        sale_item = SaleItem(
            sale_id=sale.id,
            product_id=item_data["product"].id,
            quantity=item_data["quantity"],
            price=item_data["price"],
            is_tax_exempt=item_data["is_tax_exempt"],
        )
        db.add(sale_item)
        item_data["product"].stock -= item_data["quantity"]

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
