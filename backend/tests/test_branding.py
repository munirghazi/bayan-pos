"""Phase 1 white-label — tenant branding round-trip."""
import pytest
from fastapi.testclient import TestClient
import main
from config import settings

PASSWORD = settings.bootstrap_admin_password

@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c

def h(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": "bayan"})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

def test_branding_roundtrip(client):
    hh = h(client)
    r = client.put("/api/settings/tenant", headers=hh, json={
        "primary_color": "#0F766E", "accent_color": "#F59E0B",
        "brand_name": "جمعية الاختبار", "favicon_url": "https://x/f.svg",
        "font_family": "Tajawal", "ui_radius": "rounded", "receipt_footer": "شكراً لتعاملكم"})
    assert r.status_code == 200, r.text
    got = client.get("/api/settings/tenant", headers=hh).json()
    assert got["primary_color"] == "#0F766E"
    assert got["accent_color"] == "#F59E0B"
    assert got["brand_name"] == "جمعية الاختبار"
    assert got["favicon_url"] == "https://x/f.svg"
    assert got["font_family"] == "Tajawal"
    assert got["ui_radius"] == "rounded"
    assert got["receipt_footer"] == "شكراً لتعاملكم"
    assert got["show_powered_by"] is True   # operator-controlled, default on, read-only to tenant

def test_branding_optional(client):
    hh = h(client)
    # a fresh field left unset stays null and does not break the response
    got = client.get("/api/settings/tenant", headers=hh).json()
    assert "primary_color" in got and "brand_name" in got
