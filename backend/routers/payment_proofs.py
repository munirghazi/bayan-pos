"""Bank-transfer proofs.

Uploaded BEFORE the sale/donation is issued (the document then references the
proof id). Stored outside the public /uploads folder, under
<private_storage_dir>/proofs/<tenant_id>/, and only streamed back through this
API to a logged-in user of the same tenant (RLS on payment_proofs). The file
type is checked by its content, not just its name. A proof can be used once.
"""
import hashlib
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import invoicing as inv
from config import settings
from database import get_db, PaymentProof
from routers.auth import get_current_user, User
from perms import require_perm

router = APIRouter()

_TYPES = {  # magic-bytes check -> (extension, mime)
    "pdf": (b"%PDF", "pdf", "application/pdf"),
    "png": (b"\x89PNG", "png", "image/png"),
    "jpg": (b"\xff\xd8\xff", "jpg", "image/jpeg"),
}


def _sniff(head: bytes):
    for _, (magic, ext, mime) in _TYPES.items():
        if head.startswith(magic):
            return ext, mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None, None


def _dir(tenant_id: int) -> str:
    path = os.path.join(settings.private_storage_dir, "proofs", str(int(tenant_id)))
    os.makedirs(path, mode=0o750, exist_ok=True)
    return path


def _fmt(p: PaymentProof) -> dict:
    return {"id": p.id, "original_name": p.original_name, "mime": p.mime,
            "size_bytes": p.size_bytes, "used": p.used, "used_ref": p.used_ref,
            "created_at": inv.iso_z(p.created_at)}


@router.post("/", dependencies=[Depends(require_perm("sell", "donate"))])
async def upload_proof(request: Request, file: UploadFile = File(...),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tid = getattr(request.state, "tenant_id", None)
    data = await file.read(settings.proof_max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="الملف فارغ")
    if len(data) > settings.proof_max_bytes:
        raise HTTPException(status_code=400, detail="حجم الملف أكبر من 5 ميجابايت")
    ext, mime = _sniff(data[:16])
    if not ext:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم — صورة (JPG/PNG/WEBP) أو PDF")
    stored = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(_dir(tid), stored), "wb") as f:
        f.write(data)
    p = PaymentProof(stored_name=stored, original_name=(file.filename or "")[:200] or None,
                     mime=mime, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                     uploaded_by=user.id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _fmt(p)


@router.get("/{proof_id}")
def proof_meta(proof_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(PaymentProof).filter(PaymentProof.id == proof_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="الإثبات غير موجود")
    return _fmt(p)


@router.get("/{proof_id}/file")
def proof_file(proof_id: int, request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    p = db.query(PaymentProof).filter(PaymentProof.id == proof_id).first()   # RLS: own tenant only
    if not p:
        raise HTTPException(status_code=404, detail="الإثبات غير موجود")
    path = os.path.join(_dir(request.state.tenant_id), p.stored_name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="ملف الإثبات غير موجود على الخادم")
    return FileResponse(path, media_type=p.mime,
                        headers={"Cache-Control": "private, no-store",
                                 "Content-Disposition": f'inline; filename="proof-{p.id}.{p.stored_name.rsplit(".",1)[-1]}"'})
