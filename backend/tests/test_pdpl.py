"""Wave 3 — PDPL data-subject features."""
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


def h(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": "bayan"})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _cashier(client, hh):
    client.post("/api/auth/users", headers=hh,
                json={"username": "cash_pdpl", "password": "Cash#12345", "full_name": "ك", "role": "cashier"})
    r = client.post("/api/auth/login", json={"username": "cash_pdpl", "password": "Cash#12345", "tenant": "bayan"})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_export_returns_pii_and_transactions(client):
    hh = h(client)
    cust = client.post("/api/customers/", headers=hh,
                       json={"name": "سعيد", "phone": "0500000001"}).json()
    prod = client.post("/api/products/", headers=hh, json={"name": "ماء", "price": 2, "stock": 50}).json()["id"]
    client.post("/api/sales/", headers=hh, json={
        "items": [{"product_id": prod, "quantity": 1}], "payment_method": "cash",
        "customer_id": cust["id"]})
    exp = client.get(f"/api/privacy/customer/{cust['id']}/export", headers=hh)
    assert exp.status_code == 200, exp.text
    body = exp.json()
    assert body["customer"]["name"] == "سعيد" and body["customer"]["phone"] == "0500000001"
    assert len(body["transactions"]) >= 1


def test_erase_anonymises_but_keeps_sales(client):
    hh = h(client)
    cust = client.post("/api/customers/", headers=hh,
                       json={"name": "منى", "phone": "0500000002", "email": "m@x.com"}).json()
    prod = client.post("/api/products/", headers=hh, json={"name": "تمر", "price": 5, "stock": 30}).json()["id"]
    sale = client.post("/api/sales/", headers=hh, json={
        "items": [{"product_id": prod, "quantity": 1}], "payment_method": "cash",
        "customer_id": cust["id"]}).json()
    er = client.post(f"/api/privacy/customer/{cust['id']}/erase", headers=hh)
    assert er.status_code == 200 and er.json()["erased_at"]
    # PII gone
    got = client.get(f"/api/customers/{cust['id']}", headers=hh).json()
    assert got["name"] == "عميل محذوف" and not got.get("phone")
    # sale retained
    s = client.get(f"/api/sales/{sale['id']}", headers=hh)
    assert s.status_code == 200
    # second erase is idempotent
    again = client.post(f"/api/privacy/customer/{cust['id']}/erase", headers=hh)
    assert again.status_code == 200


def test_admin_only(client):
    hh = h(client)
    ch = _cashier(client, hh)
    cust = client.post("/api/customers/", headers=hh, json={"name": "خالد"}).json()
    assert client.get(f"/api/privacy/customer/{cust['id']}/export", headers=ch).status_code in (401, 403)
    assert client.post(f"/api/privacy/customer/{cust['id']}/erase", headers=ch).status_code in (401, 403)


def test_retention_preview_and_apply(client):
    hh = h(client)
    # a customer with NO sales is eligible under any positive window
    cust = client.post("/api/customers/", headers=hh, json={"name": "قديم"}).json()
    prev = client.get("/api/privacy/retention/preview?months=1", headers=hh)
    assert prev.status_code == 200
    ids = [c["id"] for c in prev.json()["customers"]]
    assert cust["id"] in ids
    applied = client.post("/api/privacy/retention/apply?months=1", headers=hh)
    assert applied.status_code == 200 and applied.json()["erased"] >= 1
    got = client.get(f"/api/customers/{cust['id']}", headers=hh).json()
    assert got["name"] == "عميل محذوف"


def test_retention_requires_window(client):
    hh = h(client)
    # no months param and no tenant setting -> 400
    r = client.get("/api/privacy/retention/preview", headers=hh)
    assert r.status_code == 400
