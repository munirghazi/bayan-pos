from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from datetime import datetime
from database import get_db, Location, Register, RegisterClosing, Sale
from tenant_audit import tenant_audit
from routers.auth import get_current_user, require_admin, User

router = APIRouter()             # mounted at /api/locations
registers_router = APIRouter()   # mounted at /api/registers


# ===================== Schemas =====================

class LocationCreate(BaseModel):
    name: str


class LocationUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class LocationResponse(BaseModel):
    id: int
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class RegisterCreate(BaseModel):
    name: str
    location_id: int


class RegisterUpdate(BaseModel):
    name: str | None = None
    location_id: int | None = None
    is_active: bool | None = None


class RegisterResponse(BaseModel):
    id: int
    name: str
    location_id: int
    location_name: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


def _register_dict(reg: Register) -> dict:
    return {
        "id": reg.id, "name": reg.name, "location_id": reg.location_id,
        "location_name": reg.location.name if reg.location else None,
        "is_active": reg.is_active,
    }


# ===================== Locations =====================

@router.get("/", response_model=list[LocationResponse])
def list_locations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Location).filter(Location.is_active == True).all()  # noqa: E712


@router.post("/", response_model=LocationResponse)
def create_location(req: LocationCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    loc = Location(name=req.name)  # tenant_id filled by DB default
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.put("/{location_id}", response_model=LocationResponse)
def update_location(location_id: int, req: LocationUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="الفرع غير موجود")
    if req.name is not None:
        loc.name = req.name
    if req.is_active is not None:
        loc.is_active = req.is_active
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="الفرع غير موجود")
    loc.is_active = False
    db.commit()
    return {"message": "تم تعطيل الفرع"}


# ===================== Registers =====================

@registers_router.get("/", response_model=list[RegisterResponse])
def list_registers(location_id: int | None = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    q = db.query(Register).filter(Register.is_active == True)  # noqa: E712
    if location_id is not None:
        q = q.filter(Register.location_id == location_id)
    return [_register_dict(r) for r in q.all()]


@registers_router.post("/", response_model=RegisterResponse)
def create_register(req: RegisterCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    loc = db.query(Location).filter(Location.id == req.location_id).first()
    if not loc:
        raise HTTPException(status_code=400, detail="الفرع غير موجود")
    reg = Register(name=req.name, location_id=req.location_id)  # tenant_id via default
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return _register_dict(reg)


@registers_router.put("/{register_id}", response_model=RegisterResponse)
def update_register(register_id: int, req: RegisterUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    reg = db.query(Register).filter(Register.id == register_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    if req.location_id is not None:
        if not db.query(Location).filter(Location.id == req.location_id).first():
            raise HTTPException(status_code=400, detail="الفرع غير موجود")
        reg.location_id = req.location_id
    if req.name is not None:
        reg.name = req.name
    if req.is_active is not None:
        reg.is_active = req.is_active
    db.commit()
    db.refresh(reg)
    return _register_dict(reg)


@registers_router.delete("/{register_id}")
def delete_register(register_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    reg = db.query(Register).filter(Register.id == register_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    reg.is_active = False
    db.commit()
    return {"message": "تم تعطيل الصندوق"}


# ===================== Register closing / Z-report (Wave 2) =====================

class CloseRegisterRequest(BaseModel):
    counted_cash: float = 0.0
    opening_float: float = 0.0
    note: str | None = None


def _register_or_404(db, register_id):
    reg = db.query(Register).filter(Register.id == register_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    return reg


def _aggregate_since(db, register_id):
    """Totals for a register since its last closing (or all time)."""
    last = (db.query(RegisterClosing)
              .filter(RegisterClosing.register_id == register_id)
              .order_by(RegisterClosing.closed_at.desc()).first())
    since = last.closed_at if last else None
    q = db.query(Sale).filter(Sale.register_id == register_id)
    if since is not None:
        q = q.filter(Sale.created_at > since)
    sales = q.all()
    agg = {"cash": 0.0, "card": 0.0, "transfer": 0.0, "other": 0.0}
    total = 0.0
    for sale in sales:
        m = (sale.payment_method or "").lower()
        total += sale.total or 0.0
        agg[m if m in agg else "other"] += sale.total or 0.0
    return since, len(sales), total, agg


def _zreport(register_id, since, count, total, agg, opening_float=0.0,
             counted_cash=None, closed=False, closed_at=None):
    expected_cash = opening_float + agg["cash"]
    out = {
        "register_id": register_id,
        "period_from": since.isoformat() if since else None,
        "period_to": (closed_at or datetime.utcnow()).isoformat(),
        "sales_count": count,
        "total_sales": round(total, 2),
        "by_method": {k: round(v, 2) for k, v in agg.items()},
        "opening_float": round(opening_float, 2),
        "expected_cash": round(expected_cash, 2),
        "closed": closed,
    }
    if counted_cash is not None:
        out["counted_cash"] = round(counted_cash, 2)
        out["variance"] = round(counted_cash - expected_cash, 2)
    return out


@registers_router.get("/{register_id}/z-report")
def register_zreport(register_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Preview the current open totals for a register without closing it."""
    _register_or_404(db, register_id)
    since, count, total, agg = _aggregate_since(db, register_id)
    return _zreport(register_id, since, count, total, agg)


@registers_router.post("/{register_id}/close")
def close_register(register_id: int, req: CloseRegisterRequest,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Close a register: snapshot sales since the last close and record cash variance."""
    _register_or_404(db, register_id)
    since, count, total, agg = _aggregate_since(db, register_id)
    expected_cash = req.opening_float + agg["cash"]
    closing = RegisterClosing(
        register_id=register_id, opened_at=since, closed_by=user.username,
        opening_float=req.opening_float, sales_count=count, total_sales=total,
        cash_sales=agg["cash"], card_sales=agg["card"], transfer_sales=agg["transfer"],
        other_sales=agg["other"], expected_cash=expected_cash,
        counted_cash=req.counted_cash, variance=req.counted_cash - expected_cash,
        note=req.note)
    db.add(closing)
    db.commit()
    db.refresh(closing)
    tenant_audit(db, user, "register_close", target=register_id,
                 detail=f"total={round(total,2)} variance={round(req.counted_cash - expected_cash,2)}")
    return _zreport(register_id, since, count, total, agg, opening_float=req.opening_float,
                    counted_cash=req.counted_cash, closed=True, closed_at=closing.closed_at)


@registers_router.get("/{register_id}/closings")
def list_closings(register_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _register_or_404(db, register_id)
    rows = (db.query(RegisterClosing)
              .filter(RegisterClosing.register_id == register_id)
              .order_by(RegisterClosing.closed_at.desc()).all())
    return [{
        "id": r.id, "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        "closed_by": r.closed_by, "sales_count": r.sales_count,
        "total_sales": r.total_sales, "cash_sales": r.cash_sales, "card_sales": r.card_sales,
        "transfer_sales": r.transfer_sales, "other_sales": r.other_sales,
        "opening_float": r.opening_float, "expected_cash": r.expected_cash,
        "counted_cash": r.counted_cash, "variance": r.variance, "note": r.note,
    } for r in rows]
