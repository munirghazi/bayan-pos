from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db, PurchaseOrder, PurchaseOrderLine, Supplier, Product, Uom, User
from capabilities import require_purchasing
from routers.auth import get_current_user, require_admin
from routers.suppliers import require_compliant, supplier_compliance

router = APIRouter()

DRAFT, SUBMITTED, APPROVED, CANCELLED = "draft", "submitted", "approved", "cancelled"


# ===================== Schemas =====================

class POLineIn(BaseModel):
    product_id: int
    quantity: float
    uom_id: int | None = None
    unit_cost: float = 0


class POCreate(BaseModel):
    supplier_id: int
    notes: str | None = None
    lines: list[POLineIn]


class POUpdate(BaseModel):
    supplier_id: int | None = None
    notes: str | None = None
    lines: list[POLineIn] | None = None


def _uom_name(db, uom_id):
    if not uom_id:
        return None
    u = db.query(Uom).filter(Uom.id == uom_id).first()
    return u.name if u else None


def _format(db, po: PurchaseOrder) -> dict:
    lines = []
    total = 0.0
    for ln in po.lines:
        line_total = round(float(ln.quantity) * float(ln.unit_cost), 2)
        total += line_total
        lines.append({
            "id": ln.id, "product_id": ln.product_id,
            "product_name": ln.product.name if ln.product else None,
            "quantity": ln.quantity, "uom_id": ln.uom_id, "uom_name": _uom_name(db, ln.uom_id),
            "unit_cost": ln.unit_cost, "received_qty": ln.received_qty, "line_total": line_total,
        })
    sup = po.supplier
    return {
        "id": po.id, "po_number": po.po_number, "supplier_id": po.supplier_id,
        "supplier_name": sup.name if sup else None,
        "supplier_compliant": supplier_compliance(sup)["is_compliant"] if sup else False,
        "status": po.status, "notes": po.notes, "total": round(total, 2),
        "created_by": po.created_by, "approved_by": po.approved_by,
        "approved_at": po.approved_at, "created_at": po.created_at,
        "lines": lines,
    }


def _load(db, po_id) -> PurchaseOrder:
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="أمر الشراء غير موجود")
    return po


def _validate_lines(db, lines: list[POLineIn]):
    if not lines:
        raise HTTPException(status_code=400, detail="يجب إضافة بند واحد على الأقل")
    for ln in lines:
        if ln.quantity <= 0:
            raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
        if not db.query(Product).filter(Product.id == ln.product_id).first():
            raise HTTPException(status_code=400, detail=f"المنتج رقم {ln.product_id} غير موجود")


def _set_lines(db, po, lines: list[POLineIn]):
    for existing in list(po.lines):
        db.delete(existing)
    db.flush()
    for ln in lines:
        db.add(PurchaseOrderLine(
            po_id=po.id, product_id=ln.product_id, quantity=ln.quantity,
            uom_id=ln.uom_id, unit_cost=ln.unit_cost, received_qty=0,
        ))


# ===================== Routes =====================

@router.get("/")
def list_pos(status: str | None = None, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)):
    q = db.query(PurchaseOrder)
    if status:
        q = q.filter(PurchaseOrder.status == status)
    rows = q.order_by(PurchaseOrder.created_at.desc()).limit(200).all()
    return [_format(db, po) for po in rows]


@router.get("/{po_id}")
def get_po(po_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _format(db, _load(db, po_id))


@router.post("/")
def create_po(req: POCreate, db: Session = Depends(get_db),
              user: User = Depends(require_admin), _caps: dict = Depends(require_purchasing)):
    sup = db.query(Supplier).filter(Supplier.id == req.supplier_id,
                                    Supplier.is_active == True).first()  # noqa: E712
    if not sup:
        raise HTTPException(status_code=400, detail="المورّد غير موجود")
    _validate_lines(db, req.lines)

    next_no = (db.query(func.coalesce(func.max(PurchaseOrder.po_number), 0)).scalar() or 0) + 1
    po = PurchaseOrder(supplier_id=req.supplier_id, po_number=next_no, status=DRAFT,
                       notes=req.notes, created_by=user.id)
    db.add(po)
    db.flush()
    _set_lines(db, po, req.lines)
    db.commit()
    db.refresh(po)
    return _format(db, po)


@router.put("/{po_id}")
def update_po(po_id: int, req: POUpdate, db: Session = Depends(get_db),
              user: User = Depends(require_admin)):
    po = _load(db, po_id)
    if po.status != DRAFT:
        raise HTTPException(status_code=400, detail="لا يمكن تعديل أمر شراء بعد اعتماده أو إرساله")
    if req.supplier_id is not None:
        if not db.query(Supplier).filter(Supplier.id == req.supplier_id,
                                         Supplier.is_active == True).first():  # noqa: E712
            raise HTTPException(status_code=400, detail="المورّد غير موجود")
        po.supplier_id = req.supplier_id
    if req.notes is not None:
        po.notes = req.notes
    if req.lines is not None:
        _validate_lines(db, req.lines)
        _set_lines(db, po, req.lines)
    db.commit()
    db.refresh(po)
    return _format(db, po)


@router.post("/{po_id}/submit")
def submit_po(po_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_admin)):
    po = _load(db, po_id)
    if po.status != DRAFT:
        raise HTTPException(status_code=400, detail="يمكن إرسال المسودّات فقط")
    require_compliant(db, po.supplier_id)   # gate: supplier must be compliant
    po.status = SUBMITTED
    db.commit()
    db.refresh(po)
    return _format(db, po)


@router.post("/{po_id}/approve")
def approve_po(po_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    po = _load(db, po_id)
    if po.status not in (DRAFT, SUBMITTED):
        raise HTTPException(status_code=400, detail="لا يمكن اعتماد هذا الأمر في حالته الحالية")
    require_compliant(db, po.supplier_id)   # gate again at approval
    po.status = APPROVED
    po.approved_by = user.id
    po.approved_at = datetime.utcnow()
    db.commit()
    db.refresh(po)
    return _format(db, po)


@router.post("/{po_id}/cancel")
def cancel_po(po_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_admin)):
    po = _load(db, po_id)
    if po.status in (CANCELLED, "received", "closed"):
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء هذا الأمر")
    po.status = CANCELLED
    db.commit()
    db.refresh(po)
    return _format(db, po)


@router.delete("/{po_id}")
def delete_po(po_id: int, db: Session = Depends(get_db),
              user: User = Depends(require_admin)):
    po = _load(db, po_id)
    if po.status != DRAFT:
        raise HTTPException(status_code=400, detail="يمكن حذف المسودّات فقط")
    db.delete(po)
    db.commit()
    return {"message": "تم الحذف"}
