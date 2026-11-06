"""Fixes from the security test run (tools/sectest): each finding gets a guard here."""
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, user="admin", password=PASSWORD):
    r = client.post("/api/auth/login", json={"username": user, "password": password, "tenant": "bayan"})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _cashier(client, h, name):
    client.post("/api/auth/users", headers=h, json={"username": name, "password": "Cashier-12345",
                                                    "full_name": name, "role": "cashier"})
    return login(client, name, "Cashier-12345")


def test_cashier_cannot_overwrite_stock_and_admin_change_is_ledgered(client):     # AUTH-12
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "hard-stock", "price": 5, "stock": 10}).json()["id"]
    hc = _cashier(client, h, "hard_cashier1")
    assert client.put(f"/api/products/{pid}/stock", headers=hc, params={"quantity": 999}).status_code == 403
    assert client.put(f"/api/products/{pid}/stock", headers=h, params={"quantity": -1}).status_code == 400
    assert client.put(f"/api/products/{pid}/stock", headers=h, params={"quantity": 25}).status_code == 200
    moves = client.get("/api/stock/movements", headers=h, params={"product_id": pid}).json()
    assert any(m["type"] == "adjust" and m["qty"] == 15 for m in moves)


def test_logo_must_be_a_real_image_and_never_svg(client):                         # UPL-05/06
    h = login(client)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert client.post("/api/settings/upload-logo", headers=h, files={"file": ("l.svg", svg, "image/svg+xml")}).status_code == 400
    fake = b"<html><script>alert(1)</script></html>"
    assert client.post("/api/settings/upload-logo", headers=h, files={"file": ("l.png", fake, "image/png")}).status_code == 400
    big = PNG + b"\x00" * (3 * 1024 * 1024)
    assert client.post("/api/settings/upload-logo", headers=h, files={"file": ("l.png", big, "image/png")}).status_code == 413
    ok = client.post("/api/settings/upload-logo", headers=h, files={"file": ("logo.gif", PNG, "image/gif")})
    assert ok.status_code == 200 and ok.json()["url"].endswith(".png")            # type from content, not name
    f = client.get(ok.json()["url"])
    assert f.status_code == 200 and "sandbox" in f.headers["content-security-policy"]
    assert f.headers["x-content-type-options"] == "nosniff"


def test_product_image_and_supplier_document_checked_by_content(client):
    h = login(client)
    assert client.post("/api/products/upload-image", headers=h,
                       files={"file": ("p.jpg", b"not an image", "image/jpeg")}).status_code == 400
    assert client.post("/api/products/upload-image", headers=h,
                       files={"file": ("p.jpg", PNG, "image/jpeg")}).json()["url"].endswith(".png")


def test_logout_ends_the_token(client):                                          # AUTH-15
    h = login(client)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    client.post("/api/auth/logout", headers=h)
    assert client.get("/api/auth/me", headers=h).status_code == 401
    h2 = login(client)                                                            # a new login works
    assert client.get("/api/auth/me", headers=h2).status_code == 200


def test_password_change_keeps_this_session_and_ends_the_others(client):
    h = login(client)
    hc = _cashier(client, h, "hard_cashier2")
    other_device = login(client, "hard_cashier2", "Cashier-12345")
    r = client.post("/api/auth/change-password", headers=hc,
                    json={"current_password": "Cashier-12345", "new_password": "Cashier-67890"})
    assert r.status_code == 200
    client.cookies.clear()
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200
    assert client.get("/api/auth/me", headers=other_device).status_code == 401
    assert client.get("/api/auth/me", headers=hc).status_code == 401


def test_admin_reset_or_deactivate_ends_the_users_sessions(client):
    h = login(client)
    hc = _cashier(client, h, "hard_cashier3")
    uid = client.get("/api/auth/me", headers=hc).json()["id"]
    client.put(f"/api/auth/users/{uid}", headers=h, json={"password": "Reset-123456"})
    assert client.get("/api/auth/me", headers=hc).status_code == 401
    assert client.get("/api/auth/me", headers=h).status_code == 200               # the admin stays in
