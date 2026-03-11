from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Donation
from routers.auth import get_current_user, User
from datetime import datetime

router = APIRouter()


# ===================== Schemas =====================

class DonationCreate(BaseModel):
    donor_name: str | None = None
    amount: float
    note: str | None = None
    payment_method: str = "cash"
    card_ref: str | None = None


class DonationResponse(BaseModel):
    id: int
    donor_name: str | None
    amount: float
    note: str | None
    payment_method: str
    card_ref: str | None = None
    user_id: int
    user_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ===================== Routes =====================

@router.post("/", response_model=DonationResponse)
def create_donation(request: DonationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="مبلغ التبرع يجب أن يكون أكبر من صفر")

    donation = Donation(
        donor_name=request.donor_name,
        amount=request.amount,
        note=request.note,
        payment_method=request.payment_method,
        card_ref=request.card_ref,
        user_id=current_user.id,
    )
    db.add(donation)
    db.commit()
    db.refresh(donation)

    return _format_donation(donation)


@router.get("/", response_model=list[DonationResponse])
def get_donations(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    donations = db.query(Donation).order_by(Donation.created_at.desc()).offset(skip).limit(limit).all()
    return [_format_donation(d) for d in donations]


@router.get("/{donation_id}", response_model=DonationResponse)
def get_donation(donation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        raise HTTPException(status_code=404, detail="التبرع غير موجود")
    return _format_donation(donation)


@router.delete("/{donation_id}")
def delete_donation(donation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    donation = db.query(Donation).filter(Donation.id == donation_id).first()
    if not donation:
        raise HTTPException(status_code=404, detail="التبرع غير موجود")
    db.delete(donation)
    db.commit()
    return {"message": "تم حذف التبرع بنجاح"}


def _format_donation(donation: Donation) -> dict:
    return {
        "id": donation.id,
        "donor_name": donation.donor_name,
        "amount": donation.amount,
        "note": donation.note,
        "payment_method": donation.payment_method,
        "card_ref": donation.card_ref,
        "user_id": donation.user_id,
        "user_name": donation.user.full_name if donation.user else None,
        "created_at": donation.created_at,
    }
