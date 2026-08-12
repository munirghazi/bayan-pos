from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db, Sale, SaleItem, Product, Return, ReturnItem
from routers.auth import get_current_user, User
from kits import explode_to_leaves
from stock import record_movement

router = APIRouter()


# ===================== Schemas =====================

class ReturnItemIn(BaseModel):
    product_id: int
    quantity: float


class ReturnCreate(BaseModel):
    sale_id: int
    items: list[ReturnItemIn]
    reason: str | None = None
    register_id: int | None = None


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
        "total": r.total,
        "reason": r.reason,
        "created_at": r.created_at,
        "items": [
            {
                "product_id": i.product_id,
                "product_name": i.product.name if i.product else None,
                "quantity": i.quantity,
                "price": i.price,
            }
            for i in r.items
        ],
    }


# ===================== Routes =====================

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
            "product_name": prod.name if prod else None,
            "price": si.price,
            "sold": si.quantity,
            "returned": ret,
            "remaining": si.quantity - ret,
        })
    return {"sale_id": sale_id, "total": sale.total, "items": lines}


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
                  user: User = Depends(get_current_user)):
    if not req.items:
        raise HTTPException(status_code=400, detail="يجب تحديد صنف واحد على الأقل")

    sale = db.query(Sale).filter(Sale.id == req.sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="الفاتورة غير موجودة")

    sold = {si.product_id: si for si in
            db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()}
    already = _returned_map(db, sale.id)

    leaf_restock: dict[int, int] = {}
    total = 0.0
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
        total += si.price * it.quantity
        product = db.query(Product).filter(Product.id == it.product_id).first()
        # Reverse the sale's stock math: explode kits to leaves and restock leaves.
        explode_to_leaves(db, product, it.quantity, leaf_restock)
        validated.append((it.product_id, it.quantity, si.price))

    next_no = (db.query(func.coalesce(func.max(Return.credit_note_number), 0)).scalar() or 0) + 1

    ret = Return(
        sale_id=sale.id, user_id=user.id, register_id=req.register_id,
        credit_note_number=next_no, total=round(total, 2), reason=req.reason,
    )
    db.add(ret)
    db.flush()

    for pid, qty, price in validated:
        db.add(ReturnItem(return_id=ret.id, product_id=pid, quantity=qty, price=price))

    for leaf_id, qty in leaf_restock.items():
        leaf = db.query(Product).filter(Product.id == leaf_id).first()
        if leaf:
            leaf.stock = round(float(leaf.stock or 0) + float(qty), 3)
            record_movement(db, leaf, float(qty), "in", ref_type="return",
                            ref_id=ret.id, user_id=user.id)

    db.commit()
    db.refresh(ret)
    return _format_return(ret)
