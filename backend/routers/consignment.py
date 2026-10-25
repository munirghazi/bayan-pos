"""Consignment v1 — consignors, intake, consigned stock, statement, payouts."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import (get_db, Consignor, ConsignmentIntake, ConsignmentItem,
                      ConsignmentLedger, Supplier, Product)
from routers.auth import get_current_user, require_admin, User

router = APIRouter()   # mounted at /api/consignment


# ---------- schemas ----------
class ConsignorCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    supplier_id: int | None = None
    default_commission_percent: float = 0.0
    return_period_days: int | None = None
    payout_terms: str | None = None

class ConsignorUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    supplier_id: int | None = None
    default_commission_percent: float | None = None
    return_period_days: int | None = None
    payout_terms: str | None = None
    is_active: bool | None = None

class IntakeLine(BaseModel):
    product_id: int | None = None      # existing product (resale consignment)
    item_name: str | None = None       # OR a new standalone consigned item
    qty: float
    unit_price: float
    commission_percent: float | None = None   # inherits consignor default when omitted
    barcode: str | None = None

class IntakeCreate(BaseModel):
    consignor_id: int
    note: str | None = None
    lines: list[IntakeLine]

class PayoutCreate(BaseModel):
    consignor_id: int
    amount: float
    note: str | None = None


def _consignor_or_404(db, cid):
    c = db.query(Consignor).filter(Consignor.id == cid).first()
    if not c:
        raise HTTPException(status_code=404, detail="المورد/المودِع غير موجود")
    return c


def _c_dict(c):
    return {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
            "supplier_id": c.supplier_id, "is_active": c.is_active,
            "default_commission_percent": c.default_commission_percent,
            "return_period_days": c.return_period_days, "payout_terms": c.payout_terms}


# ---------- consignors ----------
@router.get("/consignors")
def list_consignors(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(Consignor).order_by(Consignor.name).all()
    return [_c_dict(c) for c in rows]


@router.post("/consignors")
def create_consignor(req: ConsignorCreate, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    if req.supplier_id is not None:
        if not db.query(Supplier).filter(Supplier.id == req.supplier_id).first():
            raise HTTPException(status_code=400, detail="المورّد غير موجود")
    c = Consignor(name=req.name.strip(), phone=req.phone, email=req.email,
                  supplier_id=req.supplier_id,
                  default_commission_percent=req.default_commission_percent or 0,
                  return_period_days=req.return_period_days, payout_terms=req.payout_terms)
    db.add(c); db.commit(); db.refresh(c)
    return _c_dict(c)


@router.put("/consignors/{cid}")
def update_consignor(cid: int, req: ConsignorUpdate, db: Session = Depends(get_db),
                     user: User = Depends(require_admin)):
    c = _consignor_or_404(db, cid)
    for f, v in req.model_dump(exclude_unset=True).items():
        setattr(c, f, v)
    db.commit(); db.refresh(c)
    return _c_dict(c)


# ---------- intake ----------
@router.post("/intake")
def create_intake(req: IntakeCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    _consignor_or_404(db, req.consignor_id)
    if not req.lines:
        raise HTTPException(status_code=400, detail="أضف صنفاً واحداً على الأقل")
    consignor = _consignor_or_404(db, req.consignor_id)
    intake = ConsignmentIntake(consignor_id=req.consignor_id, note=req.note)
    db.add(intake); db.flush()
    created = []
    for ln in req.lines:
        if ln.qty <= 0:
            raise HTTPException(status_code=400, detail="الكمية يجب أن تكون أكبر من صفر")
        commission = ln.commission_percent if ln.commission_percent is not None else (consignor.default_commission_percent or 0)
        if not (0 <= commission <= 100):
            raise HTTPException(status_code=400, detail="نسبة العمولة يجب أن تكون بين 0 و 100")
        # resolve the product: existing (resale) OR a new standalone consigned item
        pid = ln.product_id
        if pid:
            if not db.query(Product).filter(Product.id == pid).first():
                raise HTTPException(status_code=404, detail=f"المنتج رقم {pid} غير موجود")
        elif ln.item_name and ln.item_name.strip():
            prod = Product(name=ln.item_name.strip(), price=ln.unit_price, cost_price=0,
                           stock=0, is_active=True, is_consignment=True)
            db.add(prod); db.flush()
            pid = prod.id
        else:
            raise HTTPException(status_code=400, detail="اختر صنفاً موجوداً أو اكتب اسم صنف جديد")
        ci = ConsignmentItem(intake_id=intake.id, consignor_id=req.consignor_id,
                             product_id=pid, qty_received=ln.qty, qty_remaining=ln.qty,
                             unit_price=ln.unit_price, commission_percent=commission,
                             barcode=(ln.barcode.strip() if ln.barcode else None), status="active")
        db.add(ci); db.flush()
        if not ci.barcode:
            ci.barcode = f"CN{ci.id:08d}"     # auto scannable SKU
        created.append(ci)
    db.commit()
    return {"intake_id": intake.id, "items": [{"id": c.id, "barcode": c.barcode} for c in created]}


@router.get("/stock")
def consigned_stock(consignor_id: int | None = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Consigned lots still on hand (qty_remaining > 0)."""
    q = db.query(ConsignmentItem).filter(ConsignmentItem.qty_remaining > 0,
                                         ConsignmentItem.status == "active")
    if consignor_id is not None:
        q = q.filter(ConsignmentItem.consignor_id == consignor_id)
    out = []
    for ci in q.order_by(ConsignmentItem.id.desc()).all():
        prod = db.query(Product).filter(Product.id == ci.product_id).first()
        con = db.query(Consignor).filter(Consignor.id == ci.consignor_id).first()
        out.append({"id": ci.id, "consignor_id": ci.consignor_id,
                    "consignor_name": con.name if con else None,
                    "product_id": ci.product_id, "product_name": prod.name if prod else None,
                    "barcode": ci.barcode, "qty_remaining": float(ci.qty_remaining),
                    "unit_price": ci.unit_price, "commission_percent": ci.commission_percent})
    return out


@router.get("/lookup")
def lookup(code: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Resolve a scanned barcode to a consigned lot (for POS scan-to-sell)."""
    ci = db.query(ConsignmentItem).filter(
        ConsignmentItem.barcode == code.strip(),
        ConsignmentItem.status == "active",
        ConsignmentItem.qty_remaining > 0).first()
    if not ci:
        raise HTTPException(status_code=404, detail="لا يوجد صنف أمانة بهذا الباركود")
    prod = db.query(Product).filter(Product.id == ci.product_id).first()
    con = db.query(Consignor).filter(Consignor.id == ci.consignor_id).first()
    return {"id": ci.id, "consignor_id": ci.consignor_id,
            "consignor_name": con.name if con else None,
            "product_id": ci.product_id, "product_name": prod.name if prod else None,
            "barcode": ci.barcode, "qty_remaining": float(ci.qty_remaining),
            "unit_price": ci.unit_price, "commission_percent": ci.commission_percent}


class ReturnRequest(BaseModel):
    consignment_item_id: int
    qty: float
    note: str | None = None


@router.post("/return")
def return_to_consignor(req: ReturnRequest, db: Session = Depends(get_db),
                        user: User = Depends(require_admin)):
    """Return unsold consigned goods to the consignor (removes them from sellable stock)."""
    ci = db.query(ConsignmentItem).filter(ConsignmentItem.id == req.consignment_item_id).first()
    if not ci:
        raise HTTPException(status_code=404, detail="صنف الأمانة غير موجود")
    if req.qty <= 0 or round(req.qty, 3) > round(float(ci.qty_remaining), 3):
        raise HTTPException(status_code=400, detail="كمية الإرجاع غير صالحة")
    ci.qty_remaining = round(float(ci.qty_remaining) - req.qty, 3)
    ci.returned_qty = round(float(ci.returned_qty or 0) + req.qty, 3)
    if round(float(ci.qty_remaining), 3) <= 0:
        ci.status = "returned"
    db.add(ConsignmentLedger(consignor_id=ci.consignor_id, entry_type="return",
                             consignment_item_id=ci.id, amount=0,
                             note=req.note or f"إرجاع {req.qty:g}"))
    db.commit()
    return {"id": ci.id, "qty_remaining": float(ci.qty_remaining), "status": ci.status}


@router.get("/aging")
def aging(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Consigned items past their consignor's return window (due for return)."""
    rows = db.query(ConsignmentItem).filter(
        ConsignmentItem.qty_remaining > 0, ConsignmentItem.status == "active").all()
    out = []
    now = datetime.utcnow()
    for ci in rows:
        con = db.query(Consignor).filter(Consignor.id == ci.consignor_id).first()
        rpd = con.return_period_days if con else None
        days = (now - ci.created_at).days if ci.created_at else 0
        overdue = rpd is not None and days >= rpd
        if overdue:
            prod = db.query(Product).filter(Product.id == ci.product_id).first()
            out.append({"id": ci.id, "consignor_id": ci.consignor_id,
                        "consignor_name": con.name if con else None,
                        "product_name": prod.name if prod else None,
                        "qty_remaining": float(ci.qty_remaining),
                        "days_on_hand": days, "return_period_days": rpd})
    return out


# ---------- statement + payable ----------
@router.get("/consignors/{cid}/statement")
def statement(cid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _consignor_or_404(db, cid)
    rows = (db.query(ConsignmentLedger)
              .filter(ConsignmentLedger.consignor_id == cid)
              .order_by(ConsignmentLedger.created_at).all())
    accrued = sum(r.amount for r in rows if r.entry_type == "accrual")
    paid = sum(-r.amount for r in rows if r.entry_type == "payout")
    entries = [{"id": r.id, "type": r.entry_type, "sale_id": r.sale_id,
                "amount": r.amount, "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    return {"consignor_id": cid, "accrued": round(accrued, 2), "paid": round(paid, 2),
            "balance": round(accrued - paid, 2), "entries": entries}


@router.post("/payout")
def create_payout(req: PayoutCreate, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    _consignor_or_404(db, req.consignor_id)
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="المبلغ يجب أن يكون أكبر من صفر")
    entry = ConsignmentLedger(consignor_id=req.consignor_id, entry_type="payout",
                              amount=-abs(req.amount), note=req.note)
    db.add(entry); db.commit(); db.refresh(entry)
    return {"id": entry.id, "consignor_id": req.consignor_id, "amount": -abs(req.amount)}


# ---------- report ----------
@router.get("/report")
def report(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Per-consignor: on-hand value, accrued, paid, balance."""
    consignors = db.query(Consignor).order_by(Consignor.name).all()
    out = []
    for c in consignors:
        on_hand = db.execute(text(
            "SELECT COALESCE(SUM(qty_remaining * unit_price),0) FROM consignment_items "
            "WHERE consignor_id=:c AND qty_remaining > 0"), {"c": c.id}).scalar() or 0
        accrued = db.execute(text(
            "SELECT COALESCE(SUM(amount),0) FROM consignment_ledger "
            "WHERE consignor_id=:c AND entry_type='accrual'"), {"c": c.id}).scalar() or 0
        paid = db.execute(text(
            "SELECT COALESCE(-SUM(amount),0) FROM consignment_ledger "
            "WHERE consignor_id=:c AND entry_type='payout'"), {"c": c.id}).scalar() or 0
        out.append({"consignor_id": c.id, "name": c.name,
                    "on_hand_value": round(float(on_hand), 2),
                    "accrued": round(float(accrued), 2), "paid": round(float(paid), 2),
                    "balance": round(float(accrued) - float(paid), 2)})
    return out
