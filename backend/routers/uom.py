from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db, UomCategory, Uom
from routers.auth import get_current_user, require_admin, User
from uoms import convert, UomConversionError

router = APIRouter()


# ===================== Schemas =====================

class CategoryCreate(BaseModel):
    name: str
    decimal_places: int = 3


class CategoryUpdate(BaseModel):
    name: str | None = None
    decimal_places: int | None = None
    is_active: bool | None = None


class UomCreate(BaseModel):
    category_id: int
    name: str
    factor: float = 1
    is_reference: bool = False


class UomUpdate(BaseModel):
    name: str | None = None
    factor: float | None = None
    is_reference: bool | None = None
    is_active: bool | None = None


def _cat(c: UomCategory) -> dict:
    return {"id": c.id, "name": c.name, "decimal_places": c.decimal_places,
            "is_active": c.is_active}


def _uom(u: Uom) -> dict:
    return {"id": u.id, "category_id": u.category_id, "name": u.name,
            "factor": float(u.factor), "is_reference": u.is_reference,
            "is_active": u.is_active}


# ===================== Categories =====================

@router.get("/categories")
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cats = db.query(UomCategory).filter(UomCategory.is_active == True).all()  # noqa: E712
    return [_cat(c) for c in cats]


@router.post("/categories")
def create_category(req: CategoryCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    c = UomCategory(name=req.name, decimal_places=req.decimal_places)
    db.add(c); db.commit(); db.refresh(c)
    return _cat(c)


@router.put("/categories/{cat_id}")
def update_category(cat_id: int, req: CategoryUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    c = db.query(UomCategory).filter(UomCategory.id == cat_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="الفئة غير موجودة")
    for f, v in req.model_dump(exclude_unset=True).items():
        setattr(c, f, v)
    db.commit(); db.refresh(c)
    return _cat(c)


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    c = db.query(UomCategory).filter(UomCategory.id == cat_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="الفئة غير موجودة")
    c.is_active = False
    db.commit()
    return {"message": "تم التعطيل"}


# ===================== Units =====================

@router.get("/units")
def list_units(category_id: int | None = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    q = db.query(Uom).filter(Uom.is_active == True)  # noqa: E712
    if category_id is not None:
        q = q.filter(Uom.category_id == category_id)
    return [_uom(u) for u in q.order_by(Uom.category_id, Uom.factor).all()]


@router.post("/units")
def create_uom(req: UomCreate, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    if not db.query(UomCategory).filter(UomCategory.id == req.category_id).first():
        raise HTTPException(status_code=400, detail="الفئة غير موجودة")
    if req.factor <= 0:
        raise HTTPException(status_code=400, detail="المعامل يجب أن يكون أكبر من صفر")
    u = Uom(category_id=req.category_id, name=req.name, factor=req.factor,
            is_reference=req.is_reference)
    db.add(u); db.commit(); db.refresh(u)
    return _uom(u)


@router.put("/units/{uom_id}")
def update_uom(uom_id: int, req: UomUpdate, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    u = db.query(Uom).filter(Uom.id == uom_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="الوحدة غير موجودة")
    if req.factor is not None and req.factor <= 0:
        raise HTTPException(status_code=400, detail="المعامل يجب أن يكون أكبر من صفر")
    for f, v in req.model_dump(exclude_unset=True).items():
        setattr(u, f, v)
    db.commit(); db.refresh(u)
    return _uom(u)


@router.delete("/units/{uom_id}")
def delete_uom(uom_id: int, db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    u = db.query(Uom).filter(Uom.id == uom_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="الوحدة غير موجودة")
    u.is_active = False
    db.commit()
    return {"message": "تم التعطيل"}


# ===================== Convert utility =====================

@router.get("/convert")
def convert_units(qty: float, from_uom: int, to_uom: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    f = db.query(Uom).filter(Uom.id == from_uom).first()
    t = db.query(Uom).filter(Uom.id == to_uom).first()
    if not f or not t:
        raise HTTPException(status_code=404, detail="الوحدة غير موجودة")
    try:
        return {"result": convert(qty, f, t)}
    except UomConversionError as e:
        raise HTTPException(status_code=400, detail=str(e))
