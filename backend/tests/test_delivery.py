"""Delivery: email endpoint — config gate, validation, and a mocked SMTP send."""
import base64
import pytest
from fastapi.testclient import TestClient

import main
import routers.delivery as delivery
from config import settings

PASSWORD = settings.bootstrap_admin_password
PDF_B64 = base64.b64encode(b"%PDF-1.4 fake").decode()


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": "bayan"})
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_email_disabled_without_smtp(client):
    h = login(client)
    assert client.get("/api/delivery/status", headers=h).json()["email_enabled"] is False
    r = client.post("/api/delivery/email", headers=h,
                    json={"to": "a@b.com", "pdf_base64": PDF_B64})
    assert r.status_code == 400  # not configured


def test_email_sends_via_mock_smtp(client, monkeypatch):
    h = login(client)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_from", "pos@ruyya.sa")

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=20): sent["addr"] = (host, port)
        def starttls(self, context=None): sent["tls"] = True
        def login(self, u, p): sent["login"] = u
        def sendmail(self, frm, to, body):
            sent["from"], sent["to"], sent["body"] = frm, to, body
        def quit(self): sent["quit"] = True

    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)

    # invalid email rejected
    bad = client.post("/api/delivery/email", headers=h,
                      json={"to": "not-an-email", "pdf_base64": PDF_B64})
    assert bad.status_code == 400

    # valid send: PDF attached, right recipient
    r = client.post("/api/delivery/email", headers=h, json={
        "to": "donor@example.com", "subject": "فاتورتك",
        "filename": "invoice_9.pdf", "pdf_base64": PDF_B64})
    assert r.status_code == 200, r.text
    assert r.json() == {"sent": True, "to": "donor@example.com"}
    assert sent["to"] == ["donor@example.com"]
    assert "invoice_9.pdf" in sent["body"]
    assert "application/pdf" in sent["body"]
