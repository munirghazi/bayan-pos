from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (get_db, GoodsReceipt, GoodsReceiptLine, PurchaseOrder,
                      PurchaseOrderLine, Product, User)
from routers.auth import get_current_user, require_admin
from stock import record_movement, to_base_qty

router = APIRouter()

RECEIVABLE = ("approved", "receiving")


class ReceiptLineIn(BaseModel):
    po_line_id: int
    qty_received: float          # in the PO line's purchase unit
    unit_cost: float | None = None   # override; defaults to the PO line cost


class ReceiptCreate(BaseModel):
    po_id: int
    notes: str | None = None
    lines: list[ReceiptLineIn]


def _format(r: GoodsReceipt) -> dict:
    return {
        "id": r.id, "po_id": r.po_id, "received_by": r.received_by,
        "notes": r.notes, "created_at": r.created_at,
        "lines": [
            {"id": ln.id, "po_line_id": ln.po_line_id, "product_id": ln.product_id,
             "product_name": ln.product.name if ln.product else None,
             "qty_received": ln.qty_received, "base_qty": ln.base_qty,
             "unit_cost": ln.unit_cost}
            for ln in r.lines
        ],
    }


@router.get("/")
def list_receipts(po_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    q = db.query(GoodsReceipt)
    if po_id is not None:
        q = q.filter(GoodsReceipt.po_id == po_id)
    return [_format(r) for r in q.order_by(GoodsReceipt.created_at.desc()).limit(200).all()]


@router.get("/{receipt_id}")
def get_receipt(receipt_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    r = db.query(GoodsReceipt).filter(GoodsReceipt.id == receipt_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="سند الاستلام غير موجود")
    return _format(r)


@router.post("/")
def create_receipt(req: ReceiptCreate, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == req.po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="أمر الشراء غير موجود")
    if po.status not in RECEIVABLE:
        raise HTTPException(status_code=400, detail="يمكن الاستلام فقط لأمر شراء معتمد")
    if not req.lines:
        raise HTTPException(status_code=400, detail="حدّد بنداً واحداً على الأقل للاستلام")

    po_lines = {pl.id: pl for pl in po.lines}

    receipt = GoodsReceipt(po_id=po.id, received_by=user.id, notes=req.notes)
    db.add(receipt)
    db.flush()

    for rl in req.lines:
        pl = po_lines.get(rl.po_line_id)
        if not pl:
            raise HTTPException(status_code=400, detail="بند لا ينتمي لأمر الشراء")
        if rl.qty_received <= 0:
            raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
        remaining = round(float(pl.quantity) - float(pl.received_qty or 0), 3)
        if rl.qty_received > remaining + 1e-9:
            raise HTTPException(status_code=400,
                                detail=f"الكمية المستلمة تتجاوز المتبقي ({remaining:g})")

        product = db.query(Product).filter(Product.id == pl.product_id).first()
        if product.is_kit:
            raise HTTPException(status_code=400, detail="لا يمكن استلام منتج مُجمّع (kit)")

        unit_cost = rl.unit_cost if rl.unit_cost is not None else float(pl.unit_cost or 0)
        base_qty = to_base_qty(db, product, rl.qty_received, pl.uom_id)  # purchase unit -> base

        # weighted moving average cost (per base unit)
        old_stock = float(product.stock or 0)
        old_cost = float(product.cost_price or 0)
        add_cost_total = float(rl.qty_received) * float(unit_cost)   # cost of this receipt line
        new_stock = round(old_stock + base_qty, 3)
        if new_stock > 0:
            product.cost_price = round((old_stock * old_cost + add_cost_total) / new_stock, 3)
        product.stock = new_stock

        cost_per_base = round(add_cost_total / base_qty, 3) if base_qty else unit_cost
        record_movement(db, product, base_qty, "in", ref_type="goods_receipt",
                        ref_id=receipt.id, user_id=user.id, unit_cost=cost_per_base)

        pl.received_qty = round(float(pl.received_qty or 0) + float(rl.qty_received), 3)
        db.add(GoodsReceiptLine(
            receipt_id=receipt.id, po_line_id=pl.id, product_id=product.id,
            qty_received=rl.qty_received, base_qty=base_qty, unit_cost=unit_cost,
        ))

    # PO status: fully received vs partial
    fully = all(round(float(pl.received_qty or 0), 3) >= round(float(pl.quantity), 3)
                for pl in po.lines)
    po.status = "received" if fully else "receiving"

    db.commit()
    db.refresh(receipt)
    return _format(receipt)
