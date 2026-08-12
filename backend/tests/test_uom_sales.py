"""Phase 5.3c: selling in a non-base unit (price per selling unit, stock in base)."""
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


def _units(client, h):
    return {u["name"]: u for u in client.get("/api/uom/units", headers=h).json()}


def test_sell_in_pack_unit_deducts_base_and_prices_per_pack(client):
    h = login(client)
    us = _units(client, h)
    # a pack unit "شرنك" = 27 حبة in the عدد category
    cat = next(c for c in client.get("/api/uom/categories", headers=h).json() if c["name"] == "عدد")
    shrink = client.post("/api/uom/units", headers=h, json={
        "category_id": cat["id"], "name": "شرنك", "factor": 27}).json()

    # product: base = حبة, sales = شرنك, price 100 per شرنك, stock 100 حبة
    pid = client.post("/api/products/", headers=h, json={
        "name": "علبة مناديل", "price": 100, "stock": 100,
        "uom_id": us["حبة"]["id"], "sales_uom_id": shrink["id"]}).json()["id"]

    # sell 1 شرنك -> deduct 27 حبة, total = 100 (per pack)
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 1, "uom_id": shrink["id"]}],
        "payment_method": "cash"})
    assert sale.status_code == 200, sale.text
    body = sale.json()
    assert body["total"] == 100
    assert body["items"][0]["uom_name"] == "شرنك"
    assert stock_of(client, h, pid) == 73          # 100 - 27

    # ledger shows the base deduction of 27
    mv = client.get(f"/api/stock/movements?product_id={pid}", headers=h).json()
    assert any(m["type"] == "out" and m["qty"] == -27 for m in mv)

    # return 1 شرنك -> restock 27 -> back to 100
    r = client.post("/api/returns/", headers=h, json={
        "sale_id": body["id"], "items": [{"product_id": pid, "quantity": 1}]})
    assert r.status_code == 200, r.text
    assert stock_of(client, h, pid) == 100


def test_not_enough_base_stock_for_one_pack(client):
    h = login(client)
    us = _units(client, h)
    cat = next(c for c in client.get("/api/uom/categories", headers=h).json() if c["name"] == "عدد")
    shrink = next((u for u in client.get("/api/uom/units", headers=h).json() if u["name"] == "شرنك"), None) \
        or client.post("/api/uom/units", headers=h, json={"category_id": cat["id"], "name": "شرنك", "factor": 27}).json()
    pid = client.post("/api/products/", headers=h, json={
        "name": "منتج قليل", "price": 50, "stock": 10,
        "uom_id": us["حبة"]["id"], "sales_uom_id": shrink["id"]}).json()["id"]
    # 1 شرنك needs 27 حبة but only 10 available -> rejected
    bad = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 1, "uom_id": shrink["id"]}],
        "payment_method": "cash"})
    assert bad.status_code == 400
