"""Phase 5.2b: fractional (decimal) quantities — non-kit sale/return, fractional
kit components with whole-kit availability, and the kit-must-be-whole guard."""
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


def stock_of(client, h, pid):
    return next(p for p in client.get("/api/products/", headers=h).json() if p["id"] == pid)["stock"]


def test_fractional_non_kit_sale_and_return(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h,
                      json={"name": "أرز", "price": 8, "stock": 10, "unit": "كجم"}).json()["id"]
    # sell 1.5 kg -> 8.5
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 1.5}], "payment_method": "cash"})
    assert sale.status_code == 200, sale.text
    assert stock_of(client, h, pid) == 8.5
    # return 0.5 kg -> 9.0
    r = client.post("/api/returns/", headers=h, json={
        "sale_id": sale.json()["id"], "items": [{"product_id": pid, "quantity": 0.5}]})
    assert r.status_code == 200, r.text
    assert stock_of(client, h, pid) == 9.0


def test_fractional_kit_components_whole_kit(client):
    h = login(client)
    oil = client.post("/api/products/", headers=h,
                      json={"name": "زيت", "price": 5, "stock": 1.2, "unit": "لتر"}).json()["id"]
    kit = client.post("/api/products/", headers=h, json={
        "name": "سلة", "price": 40, "stock": 0, "is_kit": True,
        "components": [{"product_id": oil, "quantity": 0.25}]}).json()
    # available whole kits = floor(1.2 / 0.25) = 4
    assert kit["available_stock"] == 4

    # sell 2 kits -> consumes 0.5 L -> 0.7 left
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": kit["id"], "quantity": 2}], "payment_method": "cash"})
    assert sale.status_code == 200, sale.text
    assert stock_of(client, h, oil) == 0.7

    # a kit cannot be sold in a fractional quantity
    bad = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": kit["id"], "quantity": 1.5}], "payment_method": "cash"})
    assert bad.status_code == 400
