from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from routers.auth import get_current_user, require_admin, User
import os
import shutil

router = APIRouter()

UPLOADS_DIR = "uploads"


@router.post("/upload-logo")
async def upload_logo(file: UploadFile = File(...), current_user: User = Depends(require_admin)):
    allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم")

    filename = f"logo{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)

    # Remove old logo files
    for old in os.listdir(UPLOADS_DIR):
        if old.startswith("logo."):
            try:
                os.remove(os.path.join(UPLOADS_DIR, old))
            except OSError:
                pass

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"url": f"/uploads/{filename}"}


@router.get("/logo")
def get_logo():
    for f in os.listdir(UPLOADS_DIR):
        if f.startswith("logo."):
            return {"url": f"/uploads/{f}"}
    return {"url": ""}
