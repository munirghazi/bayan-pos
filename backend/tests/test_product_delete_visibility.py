"""Deleted (soft-deleted) products disappear from the lists but keep their history."""
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password


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


def test_deleted_product_hidden_but_history_kept(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "منتج للحذف", "price": 5, "stock": 10}).json()["id"]

    # sell it so it has history
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 2}], "payment_method": "cash"}).json()

    # delete (soft)
    assert client.delete(f"/api/products/{pid}", headers=h).status_code == 200

    ids_public = [p["id"] for p in client.get("/api/products/", headers=h).json()]
    ids_admin = [p["id"] for p in client.get("/api/products/all", headers=h).json()]
    ids_incl = [p["id"] for p in client.get("/api/products/all?include_inactive=true", headers=h).json()]

    assert pid not in ids_public          # POS list
    assert pid not in ids_admin           # Products page + Inventory dropdown
    assert pid in ids_incl                # still retrievable if explicitly asked

    # sales history still references the product by name
    got = client.get(f"/api/sales/{sale['id']}", headers=h).json()
    assert got["items"][0]["product_name"] == "منتج للحذف"

    # its stock movements are preserved in the ledger
    mv = client.get(f"/api/stock/movements?product_id={pid}", headers=h).json()
    assert any(m["type"] == "out" for m in mv)
