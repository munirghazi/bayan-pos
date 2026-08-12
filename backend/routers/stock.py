from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Product, StockMovement, User
from routers.auth import get_current_user, require_admin
from stock import record_movement, to_base_qty

router = APIRouter()


class StockIn(BaseModel):
    product_id: int
    quantity: float
    uom_id: int | None = None       # unit the quantity is entered in; converts to base
    unit_cost: float | None = None
    note: str | None = None


class StockAdjust(BaseModel):
    product_id: int
    new_quantity: float             # counted on-hand, in uom_id or base
    uom_id: int | None = None
    note: str | None = None


def _product(db, pid):
    p = db.query(Product).filter(Product.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    if p.is_kit:
        raise HTTPException(status_code=400, detail="لا يمكن تعديل مخزون منتج مُجمّع (kit) مباشرة")
    return p


def _fmt(m: StockMovement) -> dict:
    return {"id": m.id, "product_id": m.product_id, "type": m.type, "qty": m.qty,
            "balance_after": m.balance_after, "unit_cost": m.unit_cost,
            "ref_type": m.ref_type, "ref_id": m.ref_id, "note": m.note,
            "created_at": m.created_at}


@router.post("/in")
def stock_in(req: StockIn, db: Session = Depends(get_db),
             user: User = Depends(require_admin)):
    if req.quantity <= 0:
        raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
    p = _product(db, req.product_id)
    base_qty = to_base_qty(db, p, req.quantity, req.uom_id)
    p.stock = round(float(p.stock or 0) + base_qty, 3)
    record_movement(db, p, base_qty, "in", ref_type="manual", user_id=user.id,
                    unit_cost=req.unit_cost, note=req.note)
    db.commit()
    return {"product_id": p.id, "stock": p.stock, "added": base_qty}


@router.post("/adjust")
def stock_adjust(req: StockAdjust, db: Session = Depends(get_db),
                 user: User = Depends(require_admin)):
    if req.new_quantity < 0:
        raise HTTPException(status_code=400, detail="الكمية لا يمكن أن تكون سالبة")
    p = _product(db, req.product_id)
    target = to_base_qty(db, p, req.new_quantity, req.uom_id)
    delta = round(target - float(p.stock or 0), 3)
    p.stock = target
    record_movement(db, p, delta, "adjust", ref_type="adjustment", user_id=user.id,
                    note=req.note)
    db.commit()
    return {"product_id": p.id, "stock": p.stock, "delta": delta}


@router.get("/movements")
def movements(product_id: int | None = None, limit: int = 100,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(StockMovement)
    if product_id is not None:
        q = q.filter(StockMovement.product_id == product_id)
    rows = q.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()).limit(min(limit, 500)).all()
    return [_fmt(m) for m in rows]
