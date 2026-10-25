import pytest
from fastapi.testclient import TestClient
import main
from config import settings

@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c

def test_ensure_barcodes_generates_and_persists(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": settings.bootstrap_admin_password, "tenant": "bayan"})
    client.cookies.clear()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pid = client.post("/api/products/", headers=h, json={"name": "مياه", "price": 2, "stock": 5}).json()["id"]
    out = client.post("/api/products/ensure-barcodes", headers=h, json={"product_ids": [pid]}).json()
    assert len(out) == 1 and out[0]["barcode"] and out[0]["barcode"].startswith("PR")
    # persisted + idempotent
    again = client.post("/api/products/ensure-barcodes", headers=h, json={"product_ids": [pid]}).json()
    assert again[0]["barcode"] == out[0]["barcode"]
