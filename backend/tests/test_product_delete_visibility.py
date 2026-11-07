"""Products / suppliers with history are never deleted: they are archived (hidden, kept,
restorable). Archiving is refused while stock is on hand (tester: stock vanished)."""
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

    # a product with history cannot be deleted
    r = client.delete(f"/api/products/{pid}", headers=h)
    assert r.status_code == 409 and "أرشفته" in r.json()["detail"]
    use = client.get(f"/api/products/{pid}/usage", headers=h).json()
    assert use["counts"]["sales"] == 1 and use["stock"] == 8 and not use["deletable"] and not use["archivable"]
    # ... nor archived while stock is on hand
    r = client.post(f"/api/products/{pid}/archive", headers=h)
    assert r.status_code == 409 and "سوِّه" in r.json()["detail"]
    # settle the stock, then archive
    assert client.post("/api/stock/adjust", headers=h, json={"product_id": pid, "new_quantity": 0, "note": "تصفية"}).status_code == 200
    assert client.post(f"/api/products/{pid}/archive", headers=h).status_code == 200

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

    # archived products come back
    assert client.post(f"/api/products/{pid}/restore", headers=h).status_code == 200
    assert pid in [p["id"] for p in client.get("/api/products/all", headers=h).json()]


def test_unused_product_can_be_deleted_for_real(client):
    h = login(client)
    pid = client.post("/api/products/", headers=h, json={"name": "خطأ إدخال", "price": 1, "stock": 0}).json()["id"]
    assert client.get(f"/api/products/{pid}/usage", headers=h).json()["deletable"] is True
    assert client.delete(f"/api/products/{pid}", headers=h).status_code == 200
    assert pid not in [p["id"] for p in client.get("/api/products/all?include_inactive=true", headers=h).json()]


def test_component_of_active_kit_cannot_be_archived(client):
    h = login(client)
    comp = client.post("/api/products/", headers=h, json={"name": "مكوّن", "price": 1, "stock": 0}).json()["id"]
    client.post("/api/products/", headers=h, json={"name": "سلة", "price": 9, "is_kit": True,
                                                   "components": [{"product_id": comp, "quantity": 2}]})
    r = client.post(f"/api/products/{comp}/archive", headers=h)
    assert r.status_code == 409 and "مجمّع" in r.json()["detail"]


def test_supplier_with_history_is_archived_not_deleted(client):
    h = login(client)
    sid = client.post("/api/suppliers/", headers=h, json={"name": "مورّد له تعامل"}).json()["id"]
    pid = client.post("/api/products/", headers=h, json={"name": "منتج مورّد", "price": 3, "stock": 0,
                                                         "default_supplier_id": sid}).json()["id"]
    r = client.delete(f"/api/suppliers/{sid}", headers=h)
    assert r.status_code == 409 and "أرشفته" in r.json()["detail"]
    po = client.post("/api/purchase-orders/", headers=h, json={"supplier_id": sid, "lines": [{"product_id": pid, "quantity": 1, "unit_cost": 2}]})
    assert po.status_code == 200, po.text
    r = client.post(f"/api/suppliers/{sid}/archive", headers=h)
    assert r.status_code == 409 and "مفتوح" in r.json()["detail"]
    client.post(f"/api/purchase-orders/{po.json()['id']}/cancel", headers=h)
    assert client.post(f"/api/suppliers/{sid}/archive", headers=h).status_code == 200
    assert sid not in [s["id"] for s in client.get("/api/suppliers/", headers=h).json()]
    assert sid in [s["id"] for s in client.get("/api/suppliers/?archived=true", headers=h).json()]
    assert client.post(f"/api/suppliers/{sid}/restore", headers=h).status_code == 200
    # a supplier with nothing attached can be deleted for real
    empty = client.post("/api/suppliers/", headers=h, json={"name": "مورّد فارغ"}).json()["id"]
    assert client.delete(f"/api/suppliers/{empty}", headers=h).status_code == 200


def test_customer_appears_on_invoice_credit_note_and_report(client):
    h = login(client)
    cust = client.post("/api/customers/", headers=h, json={"name": "أبو غازي", "phone": "0551234567"}).json()
    pid = client.post("/api/products/", headers=h, json={"name": "منتج عميل", "price": 10, "stock": 5}).json()["id"]
    sale = client.post("/api/sales/", headers=h, json={"items": [{"product_id": pid, "quantity": 2}],
                                                       "payments": [{"method": "cash", "amount": 20}], "customer_id": cust["id"]}).json()
    assert client.get(f"/api/sales/{sale['id']}", headers=h).json()["customer_name"] == "أبو غازي"
    cn = client.post("/api/returns/", headers=h, json={"sale_id": sale["id"], "items": [{"product_id": pid, "quantity": 1}],
                                                      "reason": "تجربة", "refund_method": "cash"}).json()
    assert client.get(f"/api/returns/{cn['id']}", headers=h).json()["customer_name"] == "أبو غازي"
    rep = client.get("/api/reports/sales-report", headers=h).json()
    row = next(x for x in rep["sales"] if x["id"] == sale["id"])
    assert row["customer_name"] == "أبو غازي" and row["customer_phone"]
    cnr = next(x for x in rep["credit_notes"] if x["id"] == cn["id"])
    assert cnr["sale_id"] == sale["id"] and cnr["customer_name"] == "أبو غازي"
