"""Per-user permissions: templates, custom ticks, server enforcement, admin safety."""
import secrets

import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
PW = "Staff-Pass-123"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, user="admin", password=PASSWORD):
    r = client.post("/api/auth/login", json={"username": user, "password": password, "tenant": "bayan"})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]


def make(client, h, role, permissions=None):
    name = f"{role[:4]}_{secrets.token_hex(3)}"
    body = {"username": name, "password": PW, "full_name": name, "role": role}
    if permissions is not None:
        body["permissions"] = permissions
    r = client.post("/api/auth/users", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json(), login(client, name, PW)[0]


def test_catalog_and_templates(client):
    h, me = login(client)
    cat = client.get("/api/auth/permissions", headers=h).json()
    keys = {p["key"] for p in cat["permissions"]}
    assert {"sell", "returns", "receiving", "purchasing", "stock_adjust", "reports"} <= keys
    assert {t["key"] for t in cat["templates"]} == {"cashier", "supervisor", "storekeeper"}
    assert set(me["permissions"]) == keys and me["role_label"] == "مدير النظام"


def test_cashier_sells_but_cannot_return_report_or_adjust(client):
    h, _ = login(client)
    u, hc = make(client, h, "cashier")
    assert u["permissions"] == ["sell", "donate", "register_close"] and u["must_change_password"]
    pid = client.post("/api/products/", headers=h, json={"name": "perm-p", "price": 10, "stock": 50}).json()["id"]
    sale = client.post("/api/sales/", headers=hc, json={"items": [{"product_id": pid, "quantity": 1}],
                                                        "payments": [{"method": "cash", "amount": 10}]})
    assert sale.status_code == 200, sale.text
    r = client.post("/api/returns/", headers=hc, json={"sale_id": sale.json()["id"], "reason": "x", "refund_method": "cash",
                                                      "items": [{"product_id": pid, "quantity": 1}]})
    assert r.status_code == 403 and "المرتجعات" in r.json()["detail"]
    assert client.get("/api/reports/sales-report", headers=hc).status_code == 403
    assert client.get("/api/reports/dashboard", headers=hc).status_code == 403
    assert client.post("/api/stock/adjust", headers=hc, json={"product_id": pid, "new_quantity": 1, "note": "x"}).status_code == 403
    assert client.post("/api/products/", headers=hc, json={"name": "x", "price": 1}).status_code == 403


def test_storekeeper_manages_stock_but_cannot_sell(client):
    h, _ = login(client)
    _, hs = make(client, h, "storekeeper")
    r = client.post("/api/products/", headers=hs, json={"name": "sk-p", "price": 7, "stock": 5})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert client.post("/api/stock/adjust", headers=hs, json={"product_id": pid, "new_quantity": 9, "note": "جرد"}).status_code == 200
    assert client.post("/api/sales/", headers=hs, json={"items": [{"product_id": pid, "quantity": 1}],
                                                      "payments": [{"method": "cash", "amount": 7}]}).status_code == 403
    assert client.put("/api/settings/tenant", headers=hs, json={"receipt_footer": "x"}).status_code == 403


def test_custom_ticks_are_exact(client):
    h, _ = login(client)
    u, hx = make(client, h, "custom", ["sell", "reports"])
    assert u["permissions"] == ["sell", "reports"] and u["role_label"] == "صلاحيات مخصصة"
    assert client.get("/api/reports/sales-report", headers=hx).status_code == 200
    assert client.post("/api/donations/", headers=hx, json={"amount": 5, "payment_method": "card", "card_ref": "C"}).status_code == 403
    bad = client.post("/api/auth/users", headers=h, json={"username": "bad_" + secrets.token_hex(2), "password": PW,
                                                         "full_name": "x", "role": "custom", "permissions": ["fly"]})
    assert bad.status_code == 400
    empty = client.post("/api/auth/users", headers=h, json={"username": "emp_" + secrets.token_hex(2), "password": PW,
                                                           "full_name": "x", "role": "custom", "permissions": []})
    assert empty.status_code == 400
    assert client.post("/api/auth/users", headers=h, json={"username": "r_" + secrets.token_hex(2), "password": PW,
                                                          "full_name": "x", "role": "owner"}).status_code == 400


def test_changing_permissions_ends_the_users_session(client):
    h, _ = login(client)
    u, hc = make(client, h, "cashier")
    r = client.put(f"/api/auth/users/{u['id']}", headers=h, json={"role": "supervisor"})
    assert r.status_code == 200 and "returns" in r.json()["permissions"]
    assert client.get("/api/auth/me", headers=hc).status_code == 401
    hc2, _ = login(client, u["username"], PW)
    assert "returns" in client.get("/api/auth/me", headers=hc2).json()["permissions"]


def test_admin_cannot_lock_themselves_out(client):
    h, me = login(client)
    assert client.put(f"/api/auth/users/{me['id']}", headers=h, json={"role": "cashier"}).status_code == 400
    assert client.put(f"/api/auth/users/{me['id']}", headers=h, json={"is_active": False}).status_code == 400
    assert client.get("/api/auth/me", headers=h).status_code == 200
