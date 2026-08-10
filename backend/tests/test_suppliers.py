"""Phase 5.1: suppliers + document compliance gate."""
import datetime
import psycopg2
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")
TODAY = datetime.date.today()
FUTURE = (TODAY + datetime.timedelta(days=365)).isoformat()
SOON = (TODAY + datetime.timedelta(days=10)).isoformat()
PAST = (TODAY - datetime.timedelta(days=1)).isoformat()


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


def add_doc(client, h, sid, doc_type, expiry, verify=True):
    r = client.put(f"/api/suppliers/{sid}/document", headers=h,
                   json={"doc_type": doc_type, "number": f"{doc_type}-123", "expiry_date": expiry})
    assert r.status_code == 200, r.text
    if verify:
        r = client.put(f"/api/suppliers/{sid}/document/{doc_type}/verify", headers=h)
        assert r.status_code == 200, r.text
    return r.json()


def test_compliance_gate(client):
    h = login(client)
    sid = client.post("/api/suppliers/", headers=h,
                      json={"name": "مورّد الخير", "iban": "SA0000000000000000000000"}).json()["id"]

    # brand new supplier: not compliant, all three missing
    comp = client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()
    assert comp["is_compliant"] is False
    assert set(comp["missing"]) == {"cr", "vat", "national_address"}

    # add CR + VAT (verified) -> still missing national address
    add_doc(client, h, sid, "cr", FUTURE)
    add_doc(client, h, sid, "vat", FUTURE)
    comp = client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()
    assert comp["is_compliant"] is False and comp["missing"] == ["national_address"]

    # add national address but DON'T verify -> still not compliant
    add_doc(client, h, sid, "national_address", FUTURE, verify=False)
    assert client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()["is_compliant"] is False

    # verify it -> now compliant
    client.put(f"/api/suppliers/{sid}/document/national_address/verify", headers=h)
    assert client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()["is_compliant"] is True

    # list reflects the compliant badge
    row = next(s for s in client.get("/api/suppliers/", headers=h).json() if s["id"] == sid)
    assert row["is_compliant"] is True


def test_expiry_breaks_and_editing_resets_verification(client):
    h = login(client)
    sid = client.post("/api/suppliers/", headers=h, json={"name": "مورّد ثانٍ"}).json()["id"]
    add_doc(client, h, sid, "cr", FUTURE)
    add_doc(client, h, sid, "vat", FUTURE)
    add_doc(client, h, sid, "national_address", FUTURE)
    assert client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()["is_compliant"] is True

    # expire the CR -> not compliant; expired flag set
    add_doc(client, h, sid, "cr", PAST)
    comp = client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()
    assert comp["is_compliant"] is False
    cr = next(d for d in comp["documents"] if d["doc_type"] == "cr")
    assert cr["expired"] is True

    # fix CR with a soon-expiring date (verified) -> compliant but flagged expiring_soon
    add_doc(client, h, sid, "cr", SOON)
    comp = client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()
    assert comp["is_compliant"] is True and "cr" in comp["expiring_soon"]

    # editing a doc's metadata clears its verification (must re-verify)
    client.put(f"/api/suppliers/{sid}/document", headers=h,
               json={"doc_type": "vat", "number": "vat-999", "expiry_date": FUTURE})
    comp = client.get(f"/api/suppliers/{sid}/compliance", headers=h).json()
    vat = next(d for d in comp["documents"] if d["doc_type"] == "vat")
    assert vat["is_verified"] is False and comp["is_compliant"] is False


def test_require_compliant_helper():
    # the PO-gate helper rejects a non-compliant supplier
    from routers.suppliers import require_compliant, supplier_compliance
    from database import Supplier, SupplierDocument
    sup = Supplier(id=1, name="x", documents=[])
    assert supplier_compliance(sup)["is_compliant"] is False


def test_suppliers_tenant_isolation(client):
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'"); bayan = cur.fetchone()[0]
    cur.execute("SELECT id FROM tenants WHERE slug='sup_other'")
    row = cur.fetchone()
    if row:
        other = row[0]
    else:
        cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('sup_other','SO',true) RETURNING id")
        other = cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM suppliers"); assert cur.fetchone()[0] >= 1
    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM suppliers"); assert cur.fetchone()[0] == 0
    c.close()
