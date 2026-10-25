"""Wave 2 — register closing (Z-report), observability."""
import pytest
from fastapi.testclient import TestClient
import main
from config import settings

PASSWORD = settings.bootstrap_admin_password


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def h(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": "bayan"})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(client, hh):
    import secrets
    loc = client.get("/api/locations/", headers=hh).json()[0]["id"]
    # a fresh register so the Z-report is isolated from other tests' sales
    return client.post("/api/registers/", headers=hh,
                       json={"name": "صندوق " + secrets.token_hex(3), "location_id": loc}).json()["id"]


def test_register_close_zreport_and_variance(client):
    hh = h(client)
    rid = _register(client, hh)
    prod = client.post("/api/products/", headers=hh, json={"name": "شاي", "price": 10, "stock": 100}).json()["id"]
    # two cash sales (10 + 20) and one card sale (10) on this register
    for qty, method in [(1, "cash"), (2, "cash"), (1, "card")]:
        r = client.post("/api/sales/", headers=hh, json={
            "items": [{"product_id": prod, "quantity": qty}],
            "payment_method": method, "register_id": rid})
        assert r.status_code == 200, r.text
    # preview z-report
    z = client.get(f"/api/registers/{rid}/z-report", headers=hh).json()
    assert z["sales_count"] == 3
    assert z["by_method"]["cash"] == 30.0 and z["by_method"]["card"] == 10.0
    assert z["expected_cash"] == 30.0     # opening_float 0 + cash 30
    # close with a 5.0 short count -> variance -5
    close = client.post(f"/api/registers/{rid}/close", headers=hh,
                        json={"counted_cash": 25.0, "opening_float": 0.0, "note": "نهاية اليوم"}).json()
    assert close["closed"] is True
    assert close["counted_cash"] == 25.0 and close["variance"] == -5.0
    # after close, a fresh z-report starts empty
    z2 = client.get(f"/api/registers/{rid}/z-report", headers=hh).json()
    assert z2["sales_count"] == 0
    # closings list has the record
    lst = client.get(f"/api/registers/{rid}/closings", headers=hh).json()
    assert len(lst) >= 1 and lst[0]["variance"] == -5.0


def test_health_reports_db(client):
    r = client.get("/health")
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "up"


def test_metrics_and_timing_header(client):
    r = client.get("/health")
    assert "x-process-time-ms" in {k.lower() for k in r.headers.keys()}
    m = client.get("/metrics").json()
    assert m["requests_total"] >= 1 and "by_status_class" in m
