"""Release 2g — bundles are never bought (availability = what the components allow),
and each register session has its own report (open X report / closed Z report)."""
import secrets

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
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(client, h):
    loc = client.get("/api/locations/", headers=h).json()[0]["id"]
    return client.post("/api/registers/", headers=h,
                       json={"name": "صندوق " + secrets.token_hex(3), "location_id": loc}).json()["id"]


def _bundle(client, h, a_stock=10, b_stock=7):
    tag = secrets.token_hex(2)
    a = client.post("/api/products/", headers=h, json={"name": f"أرز {tag}", "price": 5, "stock": a_stock}).json()["id"]
    b = client.post("/api/products/", headers=h, json={"name": f"سكر {tag}", "price": 4, "stock": b_stock}).json()["id"]
    kit = client.post("/api/products/", headers=h, json={
        "name": f"سلة {tag}", "price": 30, "is_kit": True,
        "components": [{"product_id": a, "quantity": 2}, {"product_id": b, "quantity": 1}]}).json()
    return a, b, kit


def test_bundle_availability_is_the_scarcest_component(client):
    h = login(client)
    a, b, kit = _bundle(client, h, a_stock=10, b_stock=7)   # a allows 5 kits, b allows 7
    assert kit["available_stock"] == 5
    pos = {p["id"]: p for p in client.get("/api/products/", headers=h).json()}
    assert pos[kit["id"]]["available_stock"] == 5
    # selling 2 kits uses 4 of a and 2 of b -> a allows 3 more
    r = client.post("/api/sales/", headers=h, json={"items": [{"product_id": kit["id"], "quantity": 2}],
                                                    "payment_method": "cash"})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/products/{kit['id']}", headers=h).json()["available_stock"] == 3
    # asking for more than the components allow is refused
    r = client.post("/api/sales/", headers=h, json={"items": [{"product_id": kit["id"], "quantity": 4}],
                                                    "payment_method": "cash"})
    assert r.status_code == 400


def test_bundle_cannot_be_purchased_or_stocked(client):
    h = login(client)
    a, b, kit = _bundle(client, h)
    sup = client.post("/api/suppliers/", headers=h, json={"name": "مورّد سلال"}).json()["id"]
    r = client.post("/api/purchase-orders/", headers=h, json={
        "supplier_id": sup, "lines": [{"product_id": kit["id"], "quantity": 3, "unit_cost": 20}]})
    assert r.status_code == 400 and "لا يُشترى" in r.json()["detail"]
    # its components can be bought normally
    r = client.post("/api/purchase-orders/", headers=h, json={
        "supplier_id": sup, "lines": [{"product_id": a, "quantity": 3, "unit_cost": 2}]})
    assert r.status_code == 200, r.text
    # and the kit can't be swapped in by editing the draft
    r2 = client.put(f"/api/purchase-orders/{r.json()['id']}", headers=h, json={
        "lines": [{"product_id": kit["id"], "quantity": 1, "unit_cost": 20}]})
    assert r2.status_code == 400
    # no direct stock entry for a bundle
    assert client.post("/api/stock/in", headers=h, json={"product_id": kit["id"], "quantity": 5}).status_code == 400


def test_dashboard_low_stock_judges_bundles_by_components(client):
    h = login(client)
    a, b, kit = _bundle(client, h, a_stock=200, b_stock=100)          # 100 kits possible
    low = {p["id"]: p for p in client.get("/api/reports/dashboard", headers=h).json()["low_stock"]}
    assert kit["id"] not in low                                        # was always "0 left" before
    a2, b2, kit2 = _bundle(client, h, a_stock=200, b_stock=2)          # only 2 kits possible
    low = {p["id"]: p for p in client.get("/api/reports/dashboard", headers=h).json()["low_stock"]}
    assert low[kit2["id"]]["stock"] == 2 and low[kit2["id"]]["is_kit"] is True


def test_session_reports_open_and_closed(client):
    h = login(client)
    rid = _register(client, h)
    prod = client.post("/api/products/", headers=h, json={"name": "قهوة", "price": 10, "stock": 100}).json()["id"]
    cust = client.post("/api/customers/", headers=h, json={"name": "عميل الجلسة", "phone": "0551112233"}).json()["id"]
    s1 = client.post("/api/sales/", headers=h, json={"items": [{"product_id": prod, "quantity": 3}],
                                                     "payment_method": "cash", "register_id": rid,
                                                     "customer_id": cust}).json()
    client.post("/api/sales/", headers=h, json={"items": [{"product_id": prod, "quantity": 1}],
                                                "payment_method": "card", "card_ref": "A1", "register_id": rid})
    ret = client.post("/api/returns/", headers=h, json={
        "invoice_number": s1["invoice_number"], "items": [{"product_id": prod, "quantity": 1}],
        "reason": "تالف", "refund_method": "cash", "register_id": rid})
    assert ret.status_code == 200, ret.text

    cur = client.get(f"/api/registers/{rid}/sessions/current", headers=h)
    assert cur.status_code == 200, cur.text
    cur = cur.json()
    assert cur["status"] == "open" and cur["closing_id"] is None
    sm = cur["summary"]
    assert sm["sales_count"] == 2 and sm["total_sales"] == 40.0
    assert sm["by_method"]["cash"] == 30.0 and sm["by_method"]["card"] == 10.0
    assert sm["credit_notes_count"] == 1 and sm["cash_refunds"] == 10.0 and sm["net_sales"] == 30.0
    assert cur["invoices"][0]["customer_name"] == "عميل الجلسة"
    assert cur["per_cashier"][0]["sales_count"] == 2

    close = client.post(f"/api/registers/{rid}/close", headers=h,
                        json={"counted_cash": 48.0, "opening_float": 30.0, "note": "ورقة 2 ريال ناقصة"}).json()
    cid = close["closing_id"]
    # a sale after the close belongs to the next session
    client.post("/api/sales/", headers=h, json={"items": [{"product_id": prod, "quantity": 1}],
                                                "payment_method": "cash", "register_id": rid})

    z = client.get(f"/api/registers/{rid}/sessions/{cid}", headers=h).json()
    assert z["status"] == "closed" and z["closed_by"]
    assert z["summary"]["sales_count"] == 2                      # unchanged by the later sale
    assert z["summary"]["expected_cash"] == 50.0                 # 30 float + 30 cash - 10 refund
    assert z["summary"]["counted_cash"] == 48.0 and z["summary"]["variance"] == -2.0
    assert z["note"] == "ورقة 2 ريال ناقصة"

    nxt = client.get(f"/api/registers/{rid}/sessions/current", headers=h).json()
    assert nxt["summary"]["sales_count"] == 1 and nxt["period_from"] is not None

    # unknown closing / wrong register
    assert client.get(f"/api/registers/{rid}/sessions/999999", headers=h).status_code == 404
    other = _register(client, h)
    assert client.get(f"/api/registers/{other}/sessions/{cid}", headers=h).status_code == 404


def test_session_report_isolated_between_tenants(client):
    h = login(client, "bayan")
    rid = _register(client, h)
    close = client.post(f"/api/registers/{rid}/close", headers=h, json={"counted_cash": 0, "opening_float": 0}).json()
    h2 = login(client, "other")
    assert client.get(f"/api/registers/{rid}/sessions/current", headers=h2).status_code == 404
    assert client.get(f"/api/registers/{rid}/sessions/{close['closing_id']}", headers=h2).status_code == 404
