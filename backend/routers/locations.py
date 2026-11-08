from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
import re

from datetime import datetime
from database import get_db, Location, Register, RegisterClosing, Sale
from tenant_audit import tenant_audit
from routers.auth import get_current_user, require_admin, User
from perms import require_perm

router = APIRouter()             # mounted at /api/locations
registers_router = APIRouter()   # mounted at /api/registers


# ===================== Schemas =====================

class LocationCreate(BaseModel):
    name: str
    code: str | None = None       # optional; auto B01, B02 … when omitted


class LocationUpdate(BaseModel):
    name: str | None = None
    code: str | None = None       # editable only until the branch issues its first document
    is_active: bool | None = None


class LocationResponse(BaseModel):
    id: int
    name: str
    code: str | None = None
    is_active: bool
    code_locked: bool = False

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

_CODE_RE = re.compile(r"^[A-Z0-9]{1,6}$")


def _code_locked(db, location_id: int) -> bool:
    return db.execute(text(
        "SELECT EXISTS (SELECT 1 FROM document_sequences WHERE location_id = :l AND last_value > 0)"),
        {"l": location_id}).scalar()


def _loc_dict(db, loc: Location) -> dict:
    return {"id": loc.id, "name": loc.name, "code": loc.code, "is_active": loc.is_active,
            "code_locked": _code_locked(db, loc.id)}


def _clean_code(db, code: str, exclude_id: int | None = None) -> str:
    c = (code or "").strip().upper()
    if not _CODE_RE.match(c):
        raise HTTPException(status_code=400, detail="رمز الفرع: حروف إنجليزية كبيرة وأرقام فقط (حتى 6)")
    q = db.query(Location).filter(Location.code == c)
    if exclude_id is not None:
        q = q.filter(Location.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=400, detail="رمز الفرع مستخدم لفرع آخر")
    return c


@router.get("/", response_model=list[LocationResponse])
def list_locations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_loc_dict(db, l) for l in
            db.query(Location).filter(Location.is_active == True).order_by(Location.id).all()]  # noqa: E712


@router.post("/", response_model=LocationResponse)
def create_location(req: LocationCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_perm("branches"))):
    code = _clean_code(db, req.code) if req.code else None
    loc = Location(name=req.name, code=code)  # tenant_id: DB default; code: DB trigger if None
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _loc_dict(db, loc)


@router.put("/{location_id}", response_model=LocationResponse)
def update_location(location_id: int, req: LocationUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_perm("branches"))):
    loc = db.query(Location).filter(Location.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="الفرع غير موجود")
    if req.name is not None:
        loc.name = req.name
    if req.code is not None and req.code.strip().upper() != loc.code:
        if _code_locked(db, loc.id):
            raise HTTPException(status_code=400,
                                detail="لا يمكن تغيير رمز الفرع بعد إصدار أول مستند منه (تسلسل الفواتير)")
        loc.code = _clean_code(db, req.code, exclude_id=loc.id)
    if req.is_active is not None:
        loc.is_active = req.is_active
    db.commit()
    db.refresh(loc)
    return _loc_dict(db, loc)


@router.delete("/{location_id}")
def delete_location(location_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_perm("branches"))):
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
                    user: User = Depends(require_perm("branches"))):
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
                    user: User = Depends(require_perm("branches"))):
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
                    user: User = Depends(require_perm("branches"))):
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


def _last_closing(db, register_id, before=None):
    q = db.query(RegisterClosing).filter(RegisterClosing.register_id == register_id)
    if before is not None:
        q = q.filter(RegisterClosing.closed_at < before)
    return q.order_by(RegisterClosing.closed_at.desc()).first()


def _period_sales(db, register_id, since, until):
    q = db.query(Sale).filter(Sale.register_id == register_id)
    if since is not None:
        q = q.filter(Sale.created_at > since)
    if until is not None:
        q = q.filter(Sale.created_at <= until)
    return q.order_by(Sale.created_at, Sale.id).all()


def _period_returns(db, register_id, since, until, cash_only=False):
    """Credit notes issued at this register (or, when the return has no register,
    against a sale made at this register) inside the period."""
    from database import Return
    rq = (db.query(Return).join(Sale, Sale.id == Return.sale_id)
            .filter((Return.register_id == register_id) |
                    ((Return.register_id.is_(None)) & (Sale.register_id == register_id))))
    if cash_only:
        rq = rq.filter(Return.refund_method == "cash")
    if since is not None:
        rq = rq.filter(Return.created_at > since)
    if until is not None:
        rq = rq.filter(Return.created_at <= until)
    return rq.order_by(Return.created_at, Return.id).all()


def _aggregate_since(db, register_id, until=None):
    """Totals for a register since its last closing (or all time) up to `until`, per tender."""
    last = _last_closing(db, register_id, before=until)
    since = last.closed_at if last else None
    sales = _period_sales(db, register_id, since, until)
    agg = {"cash": 0.0, "card": 0.0, "transfer": 0.0, "other": 0.0}
    total = 0.0
    for sale in sales:
        total += float(sale.total or 0)
        for p in sale.payments:
            m = (p.method or "").lower()
            agg[m if m in agg else "other"] += float(p.amount or 0)
    # cash refunds paid out of this drawer (credit notes refunded in cash)
    agg["cash_refunds"] = sum(float(r.total or 0)
                              for r in _period_returns(db, register_id, since, until, cash_only=True))
    return since, len(sales), total, agg


def _zreport(register_id, since, count, total, agg, opening_float=0.0,
             counted_cash=None, closed=False, closed_at=None):
    expected_cash = opening_float + agg["cash"] - agg.get("cash_refunds", 0)
    out = {
        "register_id": register_id,
        "period_from": since.isoformat() if since else None,
        "period_to": (closed_at or datetime.utcnow()).isoformat(),
        "sales_count": count,
        "total_sales": round(total, 2),
        "by_method": {k: round(v, 2) for k, v in agg.items() if k != "cash_refunds"},
        "cash_refunds": round(agg.get("cash_refunds", 0), 2),
        "opening_float": round(opening_float, 2),
        "expected_cash": round(expected_cash, 2),
        "closed": closed,
    }
    if counted_cash is not None:
        out["counted_cash"] = round(counted_cash, 2)
        out["variance"] = round(counted_cash - expected_cash, 2)
    return out


@registers_router.get("/{register_id}/z-report", dependencies=[Depends(require_perm("register_close", "reports"))])
def register_zreport(register_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Preview the current open totals for a register without closing it."""
    _register_or_404(db, register_id)
    since, count, total, agg = _aggregate_since(db, register_id)
    return _zreport(register_id, since, count, total, agg)


@registers_router.post("/{register_id}/close", dependencies=[Depends(require_perm("register_close"))])
def close_register(register_id: int, req: CloseRegisterRequest,
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Close a register: snapshot sales since the last close and record cash variance."""
    _register_or_404(db, register_id)
    # One cut-off for both the totals and the closing time, so a sale made while
    # the close is being saved falls cleanly into the next session.
    cutoff = datetime.utcnow()
    since, count, total, agg = _aggregate_since(db, register_id, until=cutoff)
    expected_cash = req.opening_float + agg["cash"] - agg.get("cash_refunds", 0)
    closing = RegisterClosing(
        register_id=register_id, opened_at=since, closed_at=cutoff, closed_by=user.username,
        opening_float=req.opening_float, sales_count=count, total_sales=total,
        cash_sales=agg["cash"], card_sales=agg["card"], transfer_sales=agg["transfer"],
        other_sales=agg["other"], cash_refunds=agg.get("cash_refunds", 0), expected_cash=expected_cash,
        counted_cash=req.counted_cash, variance=req.counted_cash - expected_cash,
        note=req.note)
    db.add(closing)
    db.commit()
    db.refresh(closing)
    tenant_audit(db, user, "register_close", target=register_id,
                 detail=f"total={round(total,2)} variance={round(req.counted_cash - expected_cash,2)}")
    out = _zreport(register_id, since, count, total, agg, opening_float=req.opening_float,
                   counted_cash=req.counted_cash, closed=True, closed_at=closing.closed_at)
    out["closing_id"] = closing.id
    return out


@registers_router.get("/{register_id}/closings", dependencies=[Depends(require_perm("register_close", "reports"))])
def list_closings(register_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _register_or_404(db, register_id)
    from database import User as UserModel
    rows = (db.query(RegisterClosing)
              .filter(RegisterClosing.register_id == register_id)
              .order_by(RegisterClosing.closed_at.desc()).all())
    full = {u.username: (u.full_name or u.username) for u in db.query(UserModel).all()}
    return [{
        "id": r.id, "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        "closed_by": full.get(r.closed_by, r.closed_by), "sales_count": r.sales_count,
        "total_sales": r.total_sales, "cash_sales": r.cash_sales, "card_sales": r.card_sales,
        "transfer_sales": r.transfer_sales, "other_sales": r.other_sales,
        "cash_refunds": r.cash_refunds,
        "opening_float": r.opening_float, "expected_cash": r.expected_cash,
        "counted_cash": r.counted_cash, "variance": r.variance, "note": r.note,
    } for r in rows]


# ===================== Session report (one register session = between two closings) =====================

def _iso(dt):
    return dt.isoformat() if dt else None


def _session_detail(db, reg, since, until, closing=None):
    """Full report for one register session: totals, per-cashier split, invoices,
    credit notes and donations. Sales and credit notes are immutable, so a past
    session always reproduces the same figures."""
    from sqlalchemy.orm import selectinload
    from database import Donation, User as UserModel

    sq = (db.query(Sale)
            .options(selectinload(Sale.payments), selectinload(Sale.customer))
            .filter(Sale.register_id == reg.id))
    if since is not None:
        sq = sq.filter(Sale.created_at > since)
    if until is not None:
        sq = sq.filter(Sale.created_at <= until)
    sales = sq.order_by(Sale.created_at, Sale.id).all()
    returns = _period_returns(db, reg.id, since, until)
    dq = db.query(Donation).filter(Donation.register_id == reg.id)
    if since is not None:
        dq = dq.filter(Donation.created_at > since)
    if until is not None:
        dq = dq.filter(Donation.created_at <= until)
    donations = dq.order_by(Donation.created_at, Donation.id).all()

    users = db.query(UserModel).all()
    names = {u.id: (u.full_name or u.username) for u in users}
    by_username = {u.username: (u.full_name or u.username) for u in users}
    by_method = {"cash": 0.0, "card": 0.0, "transfer": 0.0, "other": 0.0}
    per_cashier: dict[str, dict] = {}
    inv_rows = []
    for s in sales:
        who = names.get(s.user_id, "—")
        pc = per_cashier.setdefault(who, {"cashier": who, "sales_count": 0, "total": 0.0,
                                          "cash": 0.0, "card": 0.0, "transfer": 0.0, "other": 0.0})
        pc["sales_count"] += 1
        pc["total"] += float(s.total or 0)
        for p in s.payments:
            m = (p.method or "").lower()
            m = m if m in by_method else "other"
            by_method[m] += float(p.amount or 0)
            pc[m] += float(p.amount or 0)
        inv_rows.append({
            "id": s.id, "invoice_number": s.invoice_number, "issued_at": _iso(s.issued_at),
            "customer_name": s.customer.name if s.customer else None,
            "payment_method": s.payment_method, "total": round(float(s.total or 0), 2),
            "vat_amount": round(float(s.vat_amount or 0), 2), "cashier": who,
        })
    cn_rows = [{
        "id": r.id, "credit_note_number": r.credit_note_number,
        "original_invoice_number": r.original_invoice_number, "sale_id": r.sale_id,
        "issued_at": _iso(r.issued_at), "refund_method": r.refund_method,
        "total": round(float(r.total or 0), 2), "reason": r.reason,
        "cashier": names.get(r.user_id, "—"),
    } for r in returns]
    don_rows = [{
        "id": d.id, "receipt_number": d.receipt_number, "issued_at": _iso(d.issued_at),
        "donor_name": d.donor_name, "payment_method": d.payment_method,
        "amount": round(float(d.amount or 0), 2), "status": d.status,
        "cashier": names.get(d.user_id, "—"),
    } for d in donations]

    total_sales = sum(float(s.total or 0) for s in sales)
    vat = sum(float(s.vat_amount or 0) for s in sales)
    cash_refunds = sum(r["total"] for r in cn_rows if r["refund_method"] == "cash")
    refunds_total = sum(r["total"] for r in cn_rows)
    donations_total = sum(d["amount"] for d in don_rows if d["status"] != "void")
    opening = float(closing.opening_float) if closing else 0.0
    expected = opening + by_method["cash"] - cash_refunds
    loc = reg.location
    out = {
        "register": {"id": reg.id, "name": reg.name,
                     "location_name": loc.name if loc else None, "location_code": loc.code if loc else None},
        "closing_id": closing.id if closing else None,
        "status": "closed" if closing else "open",
        "period_from": _iso(since), "period_to": _iso(until),
        "closed_by": (by_username.get(closing.closed_by) or closing.closed_by) if closing else None,
        "closed_at": _iso(closing.closed_at) if closing else None,
        "summary": {
            "sales_count": len(sales), "total_sales": round(total_sales, 2), "vat": round(vat, 2),
            "by_method": {k: round(v, 2) for k, v in by_method.items()},
            "credit_notes_count": len(cn_rows), "credit_notes_total": round(refunds_total, 2),
            "cash_refunds": round(cash_refunds, 2),
            "net_sales": round(total_sales - refunds_total, 2),
            "donations_count": len([d for d in don_rows if d["status"] != "void"]),
            "donations_total": round(donations_total, 2),
            "opening_float": round(opening, 2), "expected_cash": round(expected, 2),
        },
        "per_cashier": [{**v, **{k: round(v[k], 2) for k in ("total", "cash", "card", "transfer", "other")}}
                        for v in per_cashier.values()],
        "invoices": inv_rows, "credit_notes": cn_rows, "donations": don_rows,
    }
    if closing:
        # The cash count is what was recorded at closing time.
        out["summary"].update({
            "expected_cash": round(float(closing.expected_cash or 0), 2),
            "counted_cash": round(float(closing.counted_cash or 0), 2),
            "variance": round(float(closing.variance or 0), 2),
        })
        out["note"] = closing.note
    return out


@registers_router.get("/{register_id}/sessions/current",
                      dependencies=[Depends(require_perm("register_close", "reports"))])
def current_session_report(register_id: int, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """The open session (since the last closing) — an X report: nothing is closed."""
    reg = _register_or_404(db, register_id)
    now = datetime.utcnow()
    last = _last_closing(db, register_id, before=now)
    return _session_detail(db, reg, last.closed_at if last else None, now)


@registers_router.get("/{register_id}/sessions/{closing_id}",
                      dependencies=[Depends(require_perm("register_close", "reports"))])
def closed_session_report(register_id: int, closing_id: int, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """A closed session, reproduced from its closing record (the Z report)."""
    reg = _register_or_404(db, register_id)
    c = (db.query(RegisterClosing)
           .filter(RegisterClosing.id == closing_id, RegisterClosing.register_id == register_id).first())
    if not c:
        raise HTTPException(status_code=404, detail="الجلسة غير موجودة")
    prev = _last_closing(db, register_id, before=c.closed_at)
    since = prev.closed_at if prev else c.opened_at
    return _session_detail(db, reg, since, c.closed_at, closing=c)
