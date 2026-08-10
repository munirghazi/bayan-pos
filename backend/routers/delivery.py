"""Invoice delivery. Email is sent via SMTP (configured in .env). The frontend
generates the PDF and posts it here; this keeps the styled RTL receipt without
re-rendering it on the server. WhatsApp Cloud API can be added the same way once
the tenant has a WhatsApp Business number + token.
"""
import base64
import re
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import settings
from routers.auth import get_current_user, User

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailInvoice(BaseModel):
    to: str
    subject: str | None = None
    filename: str | None = None
    pdf_base64: str
    message: str | None = None


@router.get("/status")
def delivery_status(user: User = Depends(get_current_user)):
    """Lets the UI show/hide the email button based on server config."""
    return {"email_enabled": bool(settings.smtp_host), "whatsapp_enabled": False}


@router.post("/email")
def send_email(req: EmailInvoice, user: User = Depends(get_current_user)):
    if not settings.smtp_host:
        raise HTTPException(status_code=400,
                            detail="لم يتم إعداد البريد (SMTP) في الخادم")
    if not EMAIL_RE.match((req.to or "").strip()):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني غير صحيح")
    try:
        pdf = base64.b64decode((req.pdf_base64 or "").split(",")[-1])
        if not pdf:
            raise ValueError("empty")
    except Exception:
        raise HTTPException(status_code=400, detail="ملف الفاتورة غير صالح")

    from_addr = settings.smtp_from or settings.smtp_user
    msg = MIMEMultipart()
    msg["From"] = formataddr((settings.smtp_from_name or "Bayan POS", from_addr))
    msg["To"] = req.to
    msg["Subject"] = req.subject or "فاتورتك"
    msg.attach(MIMEText(req.message or "مرفق الفاتورة. شكراً لتعاملكم معنا.",
                        "plain", "utf-8"))
    part = MIMEApplication(pdf, _subtype="pdf")
    part.add_header("Content-Disposition", "attachment",
                    filename=(req.filename or "invoice.pdf"))
    msg.attach(part)

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        if settings.smtp_tls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(from_addr, [req.to], msg.as_string())
        server.quit()
    except Exception as e:  # noqa: BLE001 - surface a clean message to the UI
        raise HTTPException(status_code=502, detail=f"تعذّر إرسال البريد: {e}")

    return {"sent": True, "to": req.to}
