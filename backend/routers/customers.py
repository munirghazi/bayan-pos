from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db, Customer
from routers.auth import get_current_user, require_admin, User

router = APIRouter()


# ===================== Schemas =====================

class CustomerBase(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    vat_number: str | None = None
    address: str | None = None
    city: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    vat_number: str | None = None
    address: str | None = None
    city: str | None = None
    is_active: bool | None = None


class CustomerResponse(CustomerBase):
    id: int
    is_active: bool
    erased_at: datetime | None = None

    class Config:
        from_attributes = True


# ===================== Routes =====================

@router.get("/", response_model=list[CustomerResponse])
def list_customers(q: str | None = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    query = db.query(Customer).filter(Customer.is_active == True)  # noqa: E712
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    return query.order_by(Customer.name).limit(50).all()


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    return c


@router.post("/", response_model=CustomerResponse)
def create_customer(req: CustomerCreate, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    c = Customer(**req.model_dump())  # tenant_id filled by DB default
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{customer_id}", response_model=CustomerResponse)
def update_customer(customer_id: int, req: CustomerUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="العميل غير موجود")
    c.is_active = False
    db.commit()
    return {"message": "تم حذف العميل"}
