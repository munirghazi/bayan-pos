from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, Location, Register
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
