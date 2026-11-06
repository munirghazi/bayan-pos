"""Security tests UPL-05/06: uploaded files are checked by CONTENT, not by name.

* Only real JPEG / PNG / GIF / WebP images (and PDF where documents are allowed).
* SVG is never accepted: it is a document that can carry script.
* Size is capped while reading, so a huge upload cannot fill the disk.
* The stored extension comes from the detected type, never from the client.
"""
from fastapi import HTTPException, UploadFile

IMAGE = {"jpg", "png", "gif", "webp"}
IMAGE_OR_PDF = IMAGE | {"pdf"}


def sniff(head: bytes) -> str | None:
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"%PDF-"):
        return "pdf"
    return None


async def read_checked(file: UploadFile, allowed: set[str], max_bytes: int) -> tuple[bytes, str]:
    """Return (content, extension-with-dot) or raise 400/413."""
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"حجم الملف أكبر من المسموح ({max_bytes // (1024 * 1024)} ميجابايت)")
    kind = sniff(data[:16])
    if kind is None or kind not in allowed:
        names = {"jpg": "JPG", "png": "PNG", "gif": "GIF", "webp": "WebP", "pdf": "PDF"}
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم. المسموح: " + "، ".join(names[k] for k in sorted(allowed)))
    return data, "." + kind
