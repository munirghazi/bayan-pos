"""Consignment v1 — consignor, intake, consigned sale accrual, statement, payout."""
import pytest
from fastapi.testclient import TestClient
import main
from config import settings

PW = settings.bootstrap_admin_password

@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c

def h(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PW, "tenant": "bayan"})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

def test_consignment_end_to_end(client):
    hh = h(client)
    # a product to consign (owned stock stays untouched)
    prod = client.post("/api/products/", headers=hh, json={"name": "لوحة فنية", "price": 0, "stock": 0}).json()
    pid = prod["id"]
    # consignor (standalone)
    con = client.post("/api/consignment/consignors", headers=hh,
                      json={"name": "أم محمد", "phone": "0555"}).json()
    cid = con["id"]
    # intake: 3 units @ 100, shop commission 30%
    intake = client.post("/api/consignment/intake", headers=hh, json={
        "consignor_id": cid, "lines": [
            {"product_id": pid, "qty": 3, "unit_price": 100, "commission_percent": 30}]})
    assert intake.status_code == 200, intake.text
    # find the consigned lot
    stock = client.get(f"/api/consignment/stock?consignor_id={cid}", headers=hh).json()
    assert len(stock) == 1 and stock[0]["qty_remaining"] == 3.0
    lot = stock[0]["id"]
    # sell 2 consigned units
    sale = client.post("/api/sales/", headers=hh, json={
        "items": [{"product_id": pid, "quantity": 2, "consignment_item_id": lot}],
        "payment_method": "cash"})
    assert sale.status_code == 200, sale.text
    assert sale.json()["total"] == 200.0        # 2 × 100
    # consigned remaining reduced; owned product stock untouched (still 0)
    stock2 = client.get(f"/api/consignment/stock?consignor_id={cid}", headers=hh).json()
    assert stock2[0]["qty_remaining"] == 1.0
    assert client.get(f"/api/products/{pid}", headers=hh).json()["stock"] == 0
    # statement: consignor share = 200 × (1-0.30) = 140 accrued
    st = client.get(f"/api/consignment/consignors/{cid}/statement", headers=hh).json()
    assert st["accrued"] == 140.0 and st["balance"] == 140.0
    # payout 100 -> balance 40
    client.post("/api/consignment/payout", headers=hh, json={"consignor_id": cid, "amount": 100})
    st2 = client.get(f"/api/consignment/consignors/{cid}/statement", headers=hh).json()
    assert st2["paid"] == 100.0 and st2["balance"] == 40.0

def test_consignment_insufficient_stock(client):
    hh = h(client)
    pid = client.post("/api/products/", headers=hh, json={"name": "تحفة", "price": 0, "stock": 0}).json()["id"]
    cid = client.post("/api/consignment/consignors", headers=hh, json={"name": "بائع"}).json()["id"]
    client.post("/api/consignment/intake", headers=hh, json={
        "consignor_id": cid, "lines": [{"product_id": pid, "qty": 1, "unit_price": 50, "commission_percent": 20}]})
    lot = client.get(f"/api/consignment/stock?consignor_id={cid}", headers=hh).json()[0]["id"]
    bad = client.post("/api/sales/", headers=hh, json={
        "items": [{"product_id": pid, "quantity": 5, "consignment_item_id": lot}], "payment_method": "cash"})
    assert bad.status_code == 400

def test_consignor_can_link_supplier(client):
    hh = h(client)
    sup = client.post("/api/suppliers/", headers=hh, json={"name": "مورّد مربوط"}).json()
    con = client.post("/api/consignment/consignors", headers=hh,
                      json={"name": "مربوط", "supplier_id": sup["id"]}).json()
    assert con["supplier_id"] == sup["id"]


# ---------------- v2 (best practice) ----------------
def test_v2_terms_inheritance_and_barcode(client):
    hh = h(client)
    pid = client.post("/api/products/", headers=hh, json={"name": "كرسي", "price": 0, "stock": 0}).json()["id"]
    # consignor with default commission 25% and 30-day return window
    con = client.post("/api/consignment/consignors", headers=hh, json={
        "name": "ورشة", "default_commission_percent": 25, "return_period_days": 30}).json()
    assert con["default_commission_percent"] == 25
    # intake line omits commission -> inherits 25; barcode auto-generated
    intake = client.post("/api/consignment/intake", headers=hh, json={
        "consignor_id": con["id"], "lines": [{"product_id": pid, "qty": 2, "unit_price": 200}]})
    assert intake.status_code == 200, intake.text
    barcode = intake.json()["items"][0]["barcode"]
    assert barcode and barcode.startswith("CN")
    stock = client.get(f"/api/consignment/stock?consignor_id={con['id']}", headers=hh).json()
    assert stock[0]["commission_percent"] == 25 and stock[0]["barcode"] == barcode

def test_v2_scan_lookup_then_sell(client):
    hh = h(client)
    pid = client.post("/api/products/", headers=hh, json={"name": "طاولة", "price": 0, "stock": 0}).json()["id"]
    con = client.post("/api/consignment/consignors", headers=hh, json={"name": "نجار", "default_commission_percent": 40}).json()
    bc = client.post("/api/consignment/intake", headers=hh, json={
        "consignor_id": con["id"], "lines": [{"product_id": pid, "qty": 1, "unit_price": 500}]}).json()["items"][0]["barcode"]
    # scan resolves the lot
    lot = client.get(f"/api/consignment/lookup?code={bc}", headers=hh).json()
    assert lot["product_name"] == "طاولة" and lot["unit_price"] == 500
    # sell it -> consignor share 500*(1-0.40)=300
    sale = client.post("/api/sales/", headers=hh, json={
        "items": [{"product_id": pid, "quantity": 1, "consignment_item_id": lot["id"]}], "payment_method": "cash"})
    assert sale.status_code == 200, sale.text
    st = client.get(f"/api/consignment/consignors/{con['id']}/statement", headers=hh).json()
    assert st["accrued"] == 300.0
    # lot now sold out -> lookup 404
    assert client.get(f"/api/consignment/lookup?code={bc}", headers=hh).status_code == 404

def test_v2_return_removes_from_sellable(client):
    hh = h(client)
    pid = client.post("/api/products/", headers=hh, json={"name": "مزهرية", "price": 0, "stock": 0}).json()["id"]
    con = client.post("/api/consignment/consignors", headers=hh, json={"name": "فنان"}).json()
    lot = client.post("/api/consignment/intake", headers=hh, json={
        "consignor_id": con["id"], "lines": [{"product_id": pid, "qty": 3, "unit_price": 90, "commission_percent": 10}]}).json()["items"][0]
    # return 3 -> status returned, not sellable
    r = client.post("/api/consignment/return", headers=hh, json={"consignment_item_id": lot["id"], "qty": 3})
    assert r.status_code == 200 and r.json()["status"] == "returned"
    # no longer appears in available stock
    stock = client.get(f"/api/consignment/stock?consignor_id={con['id']}", headers=hh).json()
    assert all(s["id"] != lot["id"] for s in stock)


def test_c_new_item_creates_hidden_consignment_product(client):
    hh = h(client)
    before = len(client.get("/api/products/", headers=hh).json())
    con = client.post("/api/consignment/consignors", headers=hh, json={"name": "أم خالد", "default_commission_percent": 20}).json()
    # intake with a NEW item name (no product_id)
    r = client.post("/api/consignment/intake", headers=hh, json={
        "consignor_id": con["id"], "lines": [{"item_name": "لوحة زيتية فريدة", "qty": 1, "unit_price": 800}]})
    assert r.status_code == 200, r.text
    # the new item does NOT appear in the owned product catalog
    after = client.get("/api/products/", headers=hh).json()
    assert len(after) == before
    assert not any(p["name"] == "لوحة زيتية فريدة" for p in after)
    # but it is a consigned lot with a barcode, sellable, and accrues
    lot = client.get(f"/api/consignment/stock?consignor_id={con['id']}", headers=hh).json()[0]
    assert lot["product_name"] == "لوحة زيتية فريدة" and lot["barcode"]
    sale = client.post("/api/sales/", headers=hh, json={
        "items": [{"product_id": lot["product_id"], "quantity": 1, "consignment_item_id": lot["id"]}],
        "payment_method": "cash"})
    assert sale.status_code == 200, sale.text
    st = client.get(f"/api/consignment/consignors/{con['id']}/statement", headers=hh).json()
    assert st["accrued"] == 640.0   # 800 × (1-0.20)
