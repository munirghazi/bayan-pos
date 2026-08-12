"""Phase 5.3b: stock ledger — manual in (with UoM conversion), adjust, and
sale/return movements."""
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


def units(client, h):
    return {u["name"]: u for u in client.get("/api/uom/units", headers=h).json()}


def stock_of(client, h, pid):
    return next(p for p in client.get("/api/products/", headers=h).json() if p["id"] == pid)["stock"]


def test_manual_in_with_uom_adjust_and_ledger(client):
    h = login(client)
    us = units(client, h)
    pid = client.post("/api/products/", headers=h, json={
        "name": "دقيق", "price": 12, "stock": 10, "uom_id": us["كجم"]["id"]}).json()["id"]

    # +5 kg -> 15
    r = client.post("/api/stock/in", headers=h, json={"product_id": pid, "quantity": 5, "note": "توريد"})
    assert r.status_code == 200 and r.json()["stock"] == 15

    # +1 ton (converted) -> +1000 -> 1015
    r = client.post("/api/stock/in", headers=h, json={"product_id": pid, "quantity": 1, "uom_id": us["طن"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["stock"] == 1015

    # adjust to 20 -> stock 20, negative delta
    r = client.post("/api/stock/adjust", headers=h, json={"product_id": pid, "new_quantity": 20})
    assert r.status_code == 200 and r.json()["stock"] == 20

    mv = client.get(f"/api/stock/movements?product_id={pid}", headers=h).json()
    assert len(mv) >= 3
    assert mv[0]["type"] == "adjust"                 # most recent
    assert mv[0]["balance_after"] == 20
    assert any(m["type"] == "in" and m["qty"] == 1000 for m in mv)


def test_sale_and_return_write_movements(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "زبادي", "price": 6, "stock": 20}).json()["id"]
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 3}], "payment_method": "cash"}).json()
    r = client.post("/api/returns/", headers=h, json={
        "sale_id": sale["id"], "items": [{"product_id": pid, "quantity": 1}]})
    assert r.status_code == 200, r.text

    mv = client.get(f"/api/stock/movements?product_id={pid}", headers=h).json()
    out = next(m for m in mv if m["type"] == "out" and m["ref_type"] == "sale")
    assert out["qty"] == -3
    inc = next(m for m in mv if m["type"] == "in" and m["ref_type"] == "return")
    assert inc["qty"] == 1
    assert stock_of(client, h, pid) == 18            # 20 - 3 + 1


def test_kit_stock_in_rejected(client):
    h = login(client)
    comp = client.post("/api/products/", headers=h, json={"name": "قطعة", "price": 2, "stock": 5}).json()["id"]
    kit = client.post("/api/products/", headers=h, json={
        "name": "علبة", "price": 10, "stock": 0, "is_kit": True,
        "components": [{"product_id": comp, "quantity": 2}]}).json()["id"]
    r = client.post("/api/stock/in", headers=h, json={"product_id": kit, "quantity": 3})
    assert r.status_code == 400
