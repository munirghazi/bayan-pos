"""Phase 5.4: purchase orders — draft, compliance gate on submit/approve, edit rules, numbering."""
import datetime
import psycopg2
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")
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


def make_supplier(client, h, compliant):
    sid = client.post("/api/suppliers/", headers=h, json={"name": "مورّد PO"}).json()["id"]
    if compliant:
        for dt in ("cr", "vat", "national_address"):
            client.put(f"/api/suppliers/{sid}/document", headers=h,
                       json={"doc_type": dt, "number": f"{dt}1", "expiry_date": FUTURE})
            client.put(f"/api/suppliers/{sid}/document/{dt}/verify", headers=h)
    return sid


def test_po_flow_and_compliance_gate(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "بند شراء", "price": 5, "stock": 0}).json()["id"]

    # draft for a NON-compliant supplier is allowed
    bad_sup = make_supplier(client, h, compliant=False)
    po = client.post("/api/purchase-orders/", headers=h, json={
        "supplier_id": bad_sup, "lines": [{"product_id": pid, "quantity": 10, "unit_cost": 3}]})
    assert po.status_code == 200, po.text
    po = po.json()
    assert po["status"] == "draft" and po["total"] == 30 and po["supplier_compliant"] is False

    # but submitting it is BLOCKED by the compliance gate
    blocked = client.post(f"/api/purchase-orders/{po['id']}/submit", headers=h)
    assert blocked.status_code == 400

    # move it to a compliant supplier, then submit + approve succeed
    good_sup = make_supplier(client, h, compliant=True)
    client.put(f"/api/purchase-orders/{po['id']}", headers=h, json={"supplier_id": good_sup})
    assert client.post(f"/api/purchase-orders/{po['id']}/submit", headers=h).status_code == 200
    appr = client.post(f"/api/purchase-orders/{po['id']}/approve", headers=h)
    assert appr.status_code == 200 and appr.json()["status"] == "approved"
    assert appr.json()["approved_by"] is not None

    # cannot edit after approval
    assert client.put(f"/api/purchase-orders/{po['id']}", headers=h,
                      json={"notes": "x"}).status_code == 400


def test_po_numbering_and_delete_draft(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "بند2", "price": 5, "stock": 0}).json()["id"]
    sup = make_supplier(client, h, compliant=False)
    a = client.post("/api/purchase-orders/", headers=h, json={
        "supplier_id": sup, "lines": [{"product_id": pid, "quantity": 1, "unit_cost": 1}]}).json()
    b = client.post("/api/purchase-orders/", headers=h, json={
        "supplier_id": sup, "lines": [{"product_id": pid, "quantity": 1, "unit_cost": 1}]}).json()
    assert b["po_number"] == a["po_number"] + 1
    # draft can be deleted
    assert client.delete(f"/api/purchase-orders/{a['id']}", headers=h).status_code == 200


def test_po_isolation(client):
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'"); bayan = cur.fetchone()[0]
    cur.execute("SELECT id FROM tenants WHERE slug='po_other'")
    row = cur.fetchone()
    if row:
        other = row[0]
    else:
        cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('po_other','PO',true) RETURNING id")
        other = cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM purchase_orders"); assert cur.fetchone()[0] >= 1
    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM purchase_orders"); assert cur.fetchone()[0] == 0
    c.close()
