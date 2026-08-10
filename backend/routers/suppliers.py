import os
import shutil
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db, Supplier, SupplierDocument
from routers.auth import get_current_user, require_admin, User

router = APIRouter()

UPLOADS_DIR = "uploads"
DOC_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

# The three documents a vendor must hold to be issued a purchase order.
REQUIRED_DOCS = ["cr", "vat", "national_address"]
DOC_LABELS = {
    "cr": "السجل التجاري",
    "vat": "الشهادة الضريبية",
    "national_address": "العنوان الوطني",
}
EXPIRING_SOON_DAYS = 30


# ===================== Compliance (reused by the PO gate later) =====================

def _doc_line(doc: SupplierDocument) -> dict:
    today = date.today()
    expired = doc.expiry_date is not None and doc.expiry_date < today
    expiring_soon = (doc.expiry_date is not None and not expired
                     and doc.expiry_date <= today + timedelta(days=EXPIRING_SOON_DAYS))
    ok = bool(doc.is_verified) and not expired
    return {
        "doc_type": doc.doc_type,
        "label": DOC_LABELS.get(doc.doc_type, doc.doc_type),
        "present": True,
        "number": doc.number,
        "issue_date": doc.issue_date,
        "expiry_date": doc.expiry_date,
        "is_verified": doc.is_verified,
        "expired": expired,
        "expiring_soon": expiring_soon,
        "ok": ok,
        "file_url": doc.file_url,
    }


def supplier_compliance(supplier: Supplier) -> dict:
    """A supplier is compliant when every required doc exists, is verified, and
    is not expired. Returns per-doc detail plus overall pass/fail."""
    docs = {d.doc_type: d for d in supplier.documents}
    lines, missing, expiring = [], [], []
    all_ok = True
    for t in REQUIRED_DOCS:
        d = docs.get(t)
        if not d:
            all_ok = False
            missing.append(t)
            lines.append({
                "doc_type": t, "label": DOC_LABELS[t], "present": False,
                "number": None, "issue_date": None, "expiry_date": None,
                "is_verified": False, "expired": False, "expiring_soon": False,
                "ok": False, "file_url": None,
            })
            continue
        line = _doc_line(d)
        if not line["ok"]:
            all_ok = False
        if line["expiring_soon"]:
            expiring.append(t)
        lines.append(line)
    return {"is_compliant": all_ok, "documents": lines,
            "missing": missing, "expiring_soon": expiring}


def require_compliant(db: Session, supplier_id: int) -> Supplier:
    """Guard used by purchasing (P5.4): raise 400 if the supplier can't be issued a PO."""
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="المورّد غير موجود")
    comp = supplier_compliance(sup)
    if not comp["is_compliant"]:
        missing = "، ".join(DOC_LABELS[t] for t in comp["missing"]) or "مستندات غير صالحة"
        raise HTTPException(status_code=400,
                            detail=f"لا يمكن التعامل مع المورّد: مستندات ناقصة أو غير صالحة ({missing})")
    return sup


# ===================== Schemas =====================

class SupplierCreate(BaseModel):
    name: str
    iban: str | None = None
    payment_terms: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = None
    iban: str | None = None
    payment_terms: str | None = None
    is_active: bool | None = None


class DocumentUpsert(BaseModel):
    doc_type: str
    number: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None


def _supplier_summary(sup: Supplier) -> dict:
    return {
        "id": sup.id, "name": sup.name, "iban": sup.iban,
        "payment_terms": sup.payment_terms, "is_active": sup.is_active,
        "is_compliant": supplier_compliance(sup)["is_compliant"],
    }


def _supplier_detail(sup: Supplier) -> dict:
    return {
        "id": sup.id, "name": sup.name, "iban": sup.iban,
        "payment_terms": sup.payment_terms, "is_active": sup.is_active,
        "compliance": supplier_compliance(sup),
    }


# ===================== Supplier CRUD =====================

@router.get("/")
def list_suppliers(q: str | None = None, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    query = db.query(Supplier).filter(Supplier.is_active == True)  # noqa: E712
    if q:
        query = query.filter(or_(Supplier.name.ilike(f"%{q}%"), Supplier.iban.ilike(f"%{q}%")))
    return [_supplier_summary(s) for s in query.order_by(Supplier.name).all()]


@router.post("/")
def create_supplier(req: SupplierCreate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sup = Supplier(name=req.name, iban=req.iban, payment_terms=req.payment_terms)
    db.add(sup)
    db.commit()
    db.refresh(sup)
    return _supplier_detail(sup)


@router.get("/{supplier_id}")
def get_supplier(supplier_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="المورّد غير موجود")
    return _supplier_detail(sup)


@router.put("/{supplier_id}")
def update_supplier(supplier_id: int, req: SupplierUpdate, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="المورّد غير موجود")
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(sup, field, value)
    db.commit()
    db.refresh(sup)
    return _supplier_detail(sup)


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="المورّد غير موجود")
    sup.is_active = False
    db.commit()
    return {"message": "تم تعطيل المورّد"}


@router.get("/{supplier_id}/compliance")
def get_compliance(supplier_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="المورّد غير موجود")
    return supplier_compliance(sup)


# ===================== Documents =====================

def _get_supplier(db, supplier_id) -> Supplier:
    sup = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not sup:
        raise HTTPException(status_code=404, detail="المورّد غير موجود")
    return sup


def _upsert_doc(db, sup, doc_type) -> SupplierDocument:
    if doc_type not in REQUIRED_DOCS:
        raise HTTPException(status_code=400, detail="نوع المستند غير صحيح")
    doc = (db.query(SupplierDocument)
           .filter(SupplierDocument.supplier_id == sup.id,
                   SupplierDocument.doc_type == doc_type).first())
    if not doc:
        doc = SupplierDocument(supplier_id=sup.id, doc_type=doc_type)
        db.add(doc)
    return doc


@router.put("/{supplier_id}/document")
def upsert_document(supplier_id: int, req: DocumentUpsert, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sup = _get_supplier(db, supplier_id)
    doc = _upsert_doc(db, sup, req.doc_type)
    doc.number = req.number
    doc.issue_date = req.issue_date
    doc.expiry_date = req.expiry_date
    doc.is_verified = False  # any change requires re-verification
    db.commit()
    db.refresh(sup)
    return _supplier_detail(sup)


@router.post("/{supplier_id}/document/upload")
async def upload_document(supplier_id: int, doc_type: str = Form(...),
                          file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(require_admin)):
    sup = _get_supplier(db, supplier_id)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in DOC_EXTS:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")
    doc = _upsert_doc(db, sup, doc_type)

    folder = os.path.join(UPLOADS_DIR, f"tenant_{user.tenant_id}", "suppliers", str(sup.id))
    os.makedirs(folder, exist_ok=True)
    filename = f"{doc_type}_{uuid.uuid4().hex}{ext}"
    with open(os.path.join(folder, filename), "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    doc.file_url = f"/uploads/tenant_{user.tenant_id}/suppliers/{sup.id}/{filename}"
    doc.is_verified = False
    db.commit()
    db.refresh(sup)
    return _supplier_detail(sup)


@router.put("/{supplier_id}/document/{doc_type}/verify")
def verify_document(supplier_id: int, doc_type: str, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sup = _get_supplier(db, supplier_id)
    doc = (db.query(SupplierDocument)
           .filter(SupplierDocument.supplier_id == sup.id,
                   SupplierDocument.doc_type == doc_type).first())
    if not doc:
        raise HTTPException(status_code=404, detail="المستند غير موجود")
    doc.is_verified = True
    db.commit()
    db.refresh(sup)
    return _supplier_detail(sup)


@router.delete("/{supplier_id}/document/{doc_type}")
def delete_document(supplier_id: int, doc_type: str, db: Session = Depends(get_db),
                    user: User = Depends(require_admin)):
    sup = _get_supplier(db, supplier_id)
    doc = (db.query(SupplierDocument)
           .filter(SupplierDocument.supplier_id == sup.id,
                   SupplierDocument.doc_type == doc_type).first())
    if not doc:
        raise HTTPException(status_code=404, detail="المستند غير موجود")
    db.delete(doc)
    db.commit()
    db.refresh(sup)
    return _supplier_detail(sup)
