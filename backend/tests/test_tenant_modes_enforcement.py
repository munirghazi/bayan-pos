"""Phase 3: POS enforces per-tenant capability flags (donation/trade/mixed)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from config import settings
from database import engine

PASSWORD = settings.bootstrap_admin_password


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _set_flags(**flags):
    sets = ", ".join(f"{k} = {str(bool(v)).lower()}" for k, v in flags.items())
    with engine.begin() as c:
        c.execute(text(f"UPDATE tenants SET {sets} WHERE slug = 'bayan'"))


def _restore():
    _set_flags(sales_enabled=True, donations_enabled=True, purchasing_enabled=True)


def test_capabilities_endpoint(client):
    h = login(client)
    caps = client.get("/api/auth/capabilities", headers=h).json()
    for k in ("business_type", "sales_enabled", "donations_enabled",
              "purchasing_enabled", "vat_enabled", "inventory_enabled", "verification_status"):
        assert k in caps


def test_donation_blocked_for_trade(client):
    h = login(client)
    try:
        _set_flags(donations_enabled=False)
        r = client.post("/api/donations/", headers=h,
                        json={"amount": 100, "donor_name": "خالد", "payment_method": "cash"})
        assert r.status_code == 403
    finally:
        _restore()


def test_sale_blocked_for_donation_only(client):
    h = login(client)
    try:
        _set_flags(sales_enabled=False)
        r = client.post("/api/sales/", headers=h,
                        json={"items": [], "payment_method": "cash"})
        assert r.status_code == 403
    finally:
        _restore()


def test_purchasing_blocked_when_disabled(client):
    h = login(client)
    try:
        _set_flags(purchasing_enabled=False)
        r = client.post("/api/purchase-orders/", headers=h,
                        json={"supplier_id": 1, "items": []})
        assert r.status_code == 403
    finally:
        _restore()


def test_allowed_when_enabled(client):
    h = login(client)
    _restore()
    # donations enabled -> not 403 (may be 200/400 depending on payload, but not forbidden)
    r = client.post("/api/donations/", headers=h,
                    json={"amount": 50, "donor_name": "أحمد", "payment_method": "cash"})
    assert r.status_code != 403
