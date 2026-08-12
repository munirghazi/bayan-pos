"""Stock ledger helpers. Every stock change (sale, return, manual in, adjustment)
appends a StockMovement; manual entries may be given in any same-category unit and
are converted to the product's base unit."""
from fastapi import HTTPException

from database import StockMovement, Uom
from uoms import convert, UomConversionError


def record_movement(db, product, delta, mtype, ref_type=None, ref_id=None,
                    user_id=None, unit_cost=None, note=None):
    """Append a ledger row. Call AFTER product.stock has been updated."""
    db.add(StockMovement(
        product_id=product.id, type=mtype, qty=round(float(delta), 3),
        balance_after=round(float(product.stock or 0), 3),
        unit_cost=unit_cost, ref_type=ref_type, ref_id=ref_id,
        user_id=user_id, note=note,
    ))


def to_base_qty(db, product, quantity, uom_id):
    """Convert `quantity` (expressed in uom_id) into the product's base unit."""
    if not uom_id or not product.uom_id or int(uom_id) == int(product.uom_id):
        return round(float(quantity), 3)
    from_u = db.query(Uom).filter(Uom.id == uom_id).first()
    to_u = db.query(Uom).filter(Uom.id == product.uom_id).first()
    if not from_u or not to_u:
        raise HTTPException(status_code=400, detail="وحدة القياس غير موجودة")
    try:
        return convert(quantity, from_u, to_u)
    except UomConversionError as e:
        raise HTTPException(status_code=400, detail=str(e))
