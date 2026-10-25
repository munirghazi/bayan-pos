"""Wave 1 — security & integrity: lockout, idempotency, refund authorization + audit."""
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


def login(client, username="admin", password=PASSWORD, tenant="bayan"):
    return client.post("/api/auth/login",
                       json={"username": username, "password": password, "tenant": tenant})


def h_admin(client):
    r = login(client)
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _clear_attempts(username):
    c = psycopg2.connect(RAW_DSN); c.autocommit = True
    c.cursor().execute("DELETE FROM login_attempts WHERE username=%s", (username,))
    c.close()


# ---------- account lockout ----------
def test_account_lockout_after_repeated_failures(client):
    ghost = "ghost_user"
    _clear_attempts(ghost)
    try:
        for _ in range(settings.max_login_attempts):
            r = login(client, username=ghost, password="wrong")
            assert r.status_code == 401
        # now locked -> even a further attempt is 429
        locked = login(client, username=ghost, password="wrong")
        assert locked.status_code == 429
    finally:
        _clear_attempts(ghost)


def test_successful_login_resets_attempts(client):
    _clear_attempts("admin")
    # a couple of failures then a success clears the counter
    login(client, password="nope"); login(client, password="nope")
    ok = login(client)
    assert ok.status_code == 200
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT failed_count FROM login_attempts WHERE username='admin'")
    row = cur.fetchone(); c.close()
    assert row is None or row[0] == 0


# ---------- idempotency ----------
def test_sale_idempotency_key_dedupes(client):
    h = h_admin(client)
    prod = client.post("/api/products/", headers=h,
                       json={"name": "عصير", "price": 7, "stock": 50}).json()["id"]
    body = {"items": [{"product_id": prod, "quantity": 1}], "payment_method": "cash"}
    hh = {**h, "Idempotency-Key": "abc-123"}
    r1 = client.post("/api/sales/", headers=hh, json=body)
    r2 = client.post("/api/sales/", headers=hh, json=body)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]          # same sale, not a duplicate
    # different key -> new sale
    r3 = client.post("/api/sales/", headers={**h, "Idempotency-Key": "xyz-999"}, json=body)
    assert r3.json()["id"] != r1.json()["id"]


# ---------- refund authorization + audit ----------
def test_refund_requires_admin_and_is_audited(client):
    h = h_admin(client)
    # create a cashier (non-admin)
    client.post("/api/auth/users", headers=h,
                json={"username": "cashier1", "password": "Cash#12345", "full_name": "كاشير", "role": "cashier"})
    rc = login(client, username="cashier1", password="Cash#12345")
    client.cookies.clear()
    ch = {"Authorization": f"Bearer {rc.json()['access_token']}"}

    prod = client.post("/api/products/", headers=h,
                       json={"name": "خبز", "price": 3, "stock": 20}).json()["id"]
    sale = client.post("/api/sales/", headers=h,
                       json={"items": [{"product_id": prod, "quantity": 2}], "payment_method": "cash"}).json()

    # cashier cannot refund
    denied = client.post("/api/returns/", headers=ch,
                         json={"sale_id": sale["id"], "items": [{"product_id": prod, "quantity": 1}]})
    assert denied.status_code in (401, 403)

    # admin can, and it is audited
    ok = client.post("/api/returns/", headers=h,
                     json={"sale_id": sale["id"], "items": [{"product_id": prod, "quantity": 1}]})
    assert ok.status_code == 200, ok.text
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'")
    tid = cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(tid),))   # tenant_audit_log is RLS-protected
    cur.execute("SELECT count(*) FROM tenant_audit_log WHERE action='refund'")
    n = cur.fetchone()[0]; c.close()
    assert n >= 1
