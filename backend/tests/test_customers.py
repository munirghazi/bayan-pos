"""Phase 2: customers — CRUD, sale linkage, tenant isolation."""
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


def test_customer_crud_search_and_sale_link(client):
    h = login(client)

    c1 = client.post("/api/customers/", headers=h, json={
        "name": "أحمد محمد", "phone": "0555000111", "vat_number": "310000000000003"})
    assert c1.status_code == 200, c1.text
    cid = c1.json()["id"]

    # search by name / phone
    assert any(x["id"] == cid for x in client.get("/api/customers/?q=أحمد", headers=h).json())
    assert any(x["id"] == cid for x in client.get("/api/customers/?q=0555", headers=h).json())

    # attach to a sale
    prod = client.post("/api/products/", headers=h,
                       json={"name": "ماء", "price": 5, "stock": 100}).json()["id"]
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": prod, "quantity": 1}],
        "payment_method": "cash", "customer_id": cid})
    assert sale.status_code == 200, sale.text
    assert sale.json()["customer_id"] == cid
    assert sale.json()["customer_name"] == "أحمد محمد"

    # invalid customer rejected
    bad = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": prod, "quantity": 1}],
        "payment_method": "cash", "customer_id": 999999})
    assert bad.status_code == 400


def test_customers_tenant_isolation(client):
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'")
    bayan = cur.fetchone()[0]
    cur.execute("SELECT id FROM tenants WHERE slug='cust_other'")
    row = cur.fetchone()
    other = row[0] if row else cur.execute(
        "INSERT INTO tenants(slug,name,is_active) VALUES('cust_other','CO',true) RETURNING id") or cur.fetchone()[0]

    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM customers")
    assert cur.fetchone()[0] >= 1
    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM customers")
    assert cur.fetchone()[0] == 0
    c.close()
