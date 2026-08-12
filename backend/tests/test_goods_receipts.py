"""Phase 5.5: goods receipt — stock-in with UoM conversion, weighted-avg cost, PO status."""
import datetime
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
FUTURE = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()


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


def compliant_supplier(client, h):
    sid = client.post("/api/suppliers/", headers=h, json={"name": "مورّد استلام"}).json()["id"]
    for dt in ("cr", "vat", "national_address"):
        client.put(f"/api/suppliers/{sid}/document", headers=h,
                   json={"doc_type": dt, "number": f"{dt}1", "expiry_date": FUTURE})
        client.put(f"/api/suppliers/{sid}/document/{dt}/verify", headers=h)
    return sid


def stock_and_cost(client, h, pid):
    p = next(x for x in client.get("/api/products/all", headers=h).json() if x["id"] == pid)
    return p["stock"], p["cost_price"]


def approved_po(client, h, sup, lines):
    po = client.post("/api/purchase-orders/", headers=h,
                     json={"supplier_id": sup, "lines": lines}).json()
    client.post(f"/api/purchase-orders/{po['id']}/approve", headers=h)
    return client.get(f"/api/purchase-orders/{po['id']}", headers=h).json()


def test_full_receipt_converts_uom_and_updates_cost(client):
    h = login(client)
    us = units(client, h)
    sup = compliant_supplier(client, h)
    # base = حبة, purchase = كرتون (x24). Start with 100 حبة @ cost 5
    pid = client.post("/api/products/", headers=h, json={
        "name": "معلبات", "price": 8, "stock": 100, "cost_price": 5,
        "uom_id": us["حبة"]["id"], "purchase_uom_id": us["كرتون"]["id"]}).json()["id"]

    # PO: 10 كرتون @ 48 per carton
    po = approved_po(client, h, sup, [{
        "product_id": pid, "quantity": 10, "uom_id": us["كرتون"]["id"], "unit_cost": 48}])
    pl = po["lines"][0]

    r = client.post("/api/goods-receipts/", headers=h, json={
        "po_id": po["id"], "lines": [{"po_line_id": pl["id"], "qty_received": 10}]})
    assert r.status_code == 200, r.text

    stock, cost = stock_and_cost(client, h, pid)
    assert stock == 340                       # 100 + 10*24
    # weighted avg: (100*5 + 10*48) / 340 = (500 + 480)/340 = 2.882...
    assert abs(cost - round(980 / 340, 3)) < 0.002

    # PO fully received
    assert client.get(f"/api/purchase-orders/{po['id']}", headers=h).json()["status"] == "received"
    # ledger has an 'in' of 240 base units
    mv = client.get(f"/api/stock/movements?product_id={pid}", headers=h).json()
    assert any(m["type"] == "in" and m["qty"] == 240 and m["ref_type"] == "goods_receipt" for m in mv)


def test_partial_receipt_then_over_receive_rejected(client):
    h = login(client)
    sup = compliant_supplier(client, h)
    pid = client.post("/api/products/", headers=h, json={"name": "بسكويت", "price": 3, "stock": 0}).json()["id"]
    po = approved_po(client, h, sup, [{"product_id": pid, "quantity": 20, "unit_cost": 2}])
    pl = po["lines"][0]

    # receive 8 -> receiving, stock 8
    r = client.post("/api/goods-receipts/", headers=h, json={
        "po_id": po["id"], "lines": [{"po_line_id": pl["id"], "qty_received": 8}]})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/purchase-orders/{po['id']}", headers=h).json()["status"] == "receiving"

    # over-receive remaining (needs <=12) -> reject 15
    bad = client.post("/api/goods-receipts/", headers=h, json={
        "po_id": po["id"], "lines": [{"po_line_id": pl["id"], "qty_received": 15}]})
    assert bad.status_code == 400

    # receive remaining 12 -> received
    ok = client.post("/api/goods-receipts/", headers=h, json={
        "po_id": po["id"], "lines": [{"po_line_id": pl["id"], "qty_received": 12}]})
    assert ok.status_code == 200
    assert client.get(f"/api/purchase-orders/{po['id']}", headers=h).json()["status"] == "received"


def test_cannot_receive_unapproved_po(client):
    h = login(client)
    sup = compliant_supplier(client, h)
    pid = client.post("/api/products/", headers=h, json={"name": "شاي", "price": 4, "stock": 0}).json()["id"]
    po = client.post("/api/purchase-orders/", headers=h,
                     json={"supplier_id": sup, "lines": [{"product_id": pid, "quantity": 5, "unit_cost": 1}]}).json()
    # still draft -> cannot receive
    r = client.post("/api/goods-receipts/", headers=h, json={
        "po_id": po["id"], "lines": [{"po_line_id": po["lines"][0]["id"], "qty_received": 5}]})
    assert r.status_code == 400
