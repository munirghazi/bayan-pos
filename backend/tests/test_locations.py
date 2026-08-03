"""Phase 1 tests: locations, registers, user->branch assignment, branch-scoped sales."""
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


def login(client, tenant="bayan", username="admin", password=PASSWORD):
    r = client.post("/api/auth/login",
                    json={"username": username, "password": password, "tenant": tenant})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_default_branch_autocreated(client):
    h = login(client)
    locs = client.get("/api/locations/", headers=h).json()
    assert len(locs) == 1 and locs[0]["name"] == "الفرع الرئيسي"
    regs = client.get("/api/registers/", headers=h).json()
    assert len(regs) == 1 and regs[0]["location_id"] == locs[0]["id"]


def test_branch_scoped_sales(client):
    h = login(client)
    main_loc = client.get("/api/locations/", headers=h).json()[0]["id"]
    main_reg = client.get("/api/registers/", headers=h).json()[0]["id"]

    # second branch + register
    loc_b = client.post("/api/locations/", headers=h, json={"name": "فرع ثاني"}).json()["id"]
    reg_b = client.post("/api/registers/", headers=h,
                        json={"name": "صندوق ب", "location_id": loc_b}).json()["id"]

    prod = client.post("/api/products/", headers=h,
                       json={"name": "ماء", "price": 5, "stock": 100}).json()["id"]

    # cashier assigned to the MAIN branch
    cu = client.post("/api/auth/users", headers=h, json={
        "username": "cashier1", "password": "Cash#12345", "full_name": "كاشير",
        "role": "cashier", "location_id": main_loc})
    assert cu.status_code == 200, cu.text
    assert cu.json()["location_id"] == main_loc

    hc = login(client, username="cashier1", password="Cash#12345")

    # sells on own branch register -> ok, sale tagged with the register
    ok = client.post("/api/sales/", headers=hc, json={
        "items": [{"product_id": prod, "quantity": 1}], "payment_method": "cash",
        "register_id": main_reg})
    assert ok.status_code == 200, ok.text
    assert ok.json()["register_id"] == main_reg

    # cannot sell on another branch's register
    bad = client.post("/api/sales/", headers=hc, json={
        "items": [{"product_id": prod, "quantity": 1}], "payment_method": "cash",
        "register_id": reg_b})
    assert bad.status_code == 403

    # admin (no branch) can sell on any register
    adm = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": prod, "quantity": 1}], "payment_method": "cash",
        "register_id": reg_b})
    assert adm.status_code == 200, adm.text


def test_locations_tenant_isolation(client):
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'")
    bayan = cur.fetchone()[0]
    cur.execute("SELECT id FROM tenants WHERE slug='loc_other'")
    row = cur.fetchone()
    if row:
        other = row[0]
    else:
        cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('loc_other','LO',true) RETURNING id")
        other = cur.fetchone()[0]

    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM locations")
    assert cur.fetchone()[0] >= 1
    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM locations")
    assert cur.fetchone()[0] == 0
    c.close()
