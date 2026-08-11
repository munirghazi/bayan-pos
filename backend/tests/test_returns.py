"""Phase 2: returns / credit notes — restock, partial/over-return, kits, numbering, isolation."""
import psycopg2
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _stock(client, h, pid):
    return next(p for p in client.get("/api/products/", headers=h).json() if p["id"] == pid)["stock"]


def test_full_and_partial_returns_restock(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "ماء", "price": 10, "stock": 100}).json()["id"]

    # sell 5 -> stock 95
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 5}], "payment_method": "cash"}).json()
    assert _stock(client, h, pid) == 95

    # returnable shows 5 remaining
    ra = client.get(f"/api/returns/sale/{sale['id']}", headers=h).json()
    assert ra["items"][0]["remaining"] == 5

    # partial return of 2 -> stock 97, refund 20, credit note #1
    r1 = client.post("/api/returns/", headers=h, json={
        "sale_id": sale["id"], "items": [{"product_id": pid, "quantity": 2}], "reason": "تالف"})
    assert r1.status_code == 200, r1.text
    n1 = r1.json()["credit_note_number"]
    assert r1.json()["total"] == 20.0
    assert _stock(client, h, pid) == 97

    # over-return (4 > remaining 3) rejected
    bad = client.post("/api/returns/", headers=h, json={
        "sale_id": sale["id"], "items": [{"product_id": pid, "quantity": 4}]})
    assert bad.status_code == 400

    # return remaining 3 -> stock back to 100, credit note #2
    r2 = client.post("/api/returns/", headers=h, json={
        "sale_id": sale["id"], "items": [{"product_id": pid, "quantity": 3}]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["credit_note_number"] == n1 + 1
    assert _stock(client, h, pid) == 100

    # nothing left to return
    assert client.get(f"/api/returns/sale/{sale['id']}", headers=h).json()["items"][0]["remaining"] == 0


def test_kit_return_restocks_components(client):
    h = login(client)
    comp = client.post("/api/products/", headers=h, json={"name": "مكوّن", "price": 4, "stock": 50}).json()["id"]
    kit = client.post("/api/products/", headers=h, json={
        "name": "سلة", "price": 30, "stock": 0, "is_kit": True,
        "components": [{"product_id": comp, "quantity": 3}]}).json()["id"]

    # sell 2 kits -> 6 components consumed -> 44
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": kit, "quantity": 2}], "payment_method": "cash"}).json()
    assert _stock(client, h, comp) == 44

    # return 1 kit -> 3 components restocked -> 47
    r = client.post("/api/returns/", headers=h, json={
        "sale_id": sale["id"], "items": [{"product_id": kit, "quantity": 1}]})
    assert r.status_code == 200, r.text
    assert _stock(client, h, comp) == 47


def test_returns_tenant_isolation(client):
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'"); bayan = cur.fetchone()[0]
    cur.execute("SELECT id FROM tenants WHERE slug='ret_other'")
    row = cur.fetchone()
    if row:
        other = row[0]
    else:
        cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('ret_other','RO',true) RETURNING id")
        other = cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM returns")
    assert cur.fetchone()[0] >= 1
    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM returns")
    assert cur.fetchone()[0] == 0
    c.close()
