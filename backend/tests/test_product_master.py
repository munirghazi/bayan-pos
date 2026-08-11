"""Phase 5.2: product master fields (cost, unit, reorder, default supplier, barcode)."""
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

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


def test_create_with_master_fields_and_low_stock(client):
    h = login(client)
    sup = client.post("/api/suppliers/", headers=h, json={"name": "مورّد المنتجات"}).json()["id"]

    p = client.post("/api/products/", headers=h, json={
        "name": "أرز", "price": 20, "stock": 8,
        "barcode": "6281000000015", "cost_price": 14.5, "unit": "كيس",
        "reorder_level": 10, "default_supplier_id": sup}).json()
    assert p["barcode"] == "6281000000015"
    assert p["cost_price"] == 14.5 and p["unit"] == "كيس"
    assert p["reorder_level"] == 10 and p["default_supplier_id"] == sup
    # stock 8 <= reorder 10 -> low stock
    assert p["is_low_stock"] is True

    # raise stock above reorder -> not low
    up = client.put(f"/api/products/{p['id']}", headers=h, json={"stock": 25}).json()
    assert up["is_low_stock"] is False

    # no reorder level -> never low
    p2 = client.post("/api/products/", headers=h, json={"name": "ملح", "price": 3, "stock": 0}).json()
    assert p2["reorder_level"] == 0 and p2["is_low_stock"] is False


def test_update_cost_and_supplier(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "سكر", "price": 10, "stock": 5}).json()["id"]
    up = client.put(f"/api/products/{pid}", headers=h,
                    json={"cost_price": 7.25, "unit": "كجم", "reorder_level": 3}).json()
    assert up["cost_price"] == 7.25 and up["unit"] == "كجم" and up["reorder_level"] == 3
