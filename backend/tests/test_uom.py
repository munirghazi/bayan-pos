"""Phase 5.3a: UoM engine — default seed, conversion, product assignment, isolation."""
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


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def units(client, h):
    return {u["name"]: u for u in client.get("/api/uom/units", headers=h).json()}


def test_default_seed(client):
    h = login(client)
    cats = {c["name"]: c for c in client.get("/api/uom/categories", headers=h).json()}
    assert {"عدد", "وزن", "حجم"} <= set(cats)
    assert cats["عدد"]["decimal_places"] == 0
    assert cats["وزن"]["decimal_places"] == 3
    us = units(client, h)
    assert {"حبة", "دستة", "كرتون", "كجم", "جرام", "طن", "لتر", "مل"} <= set(us)


def test_convert_within_category_and_cross_reject(client):
    h = login(client)
    us = units(client, h)
    r = client.get(f"/api/uom/convert?qty=1&from_uom={us['كرتون']['id']}&to_uom={us['حبة']['id']}",
                   headers=h).json()
    assert r["result"] == 24            # 1 carton = 24 pieces
    r = client.get(f"/api/uom/convert?qty=1&from_uom={us['كجم']['id']}&to_uom={us['جرام']['id']}",
                   headers=h).json()
    assert r["result"] == 1000          # 1 kg = 1000 g
    r = client.get(f"/api/uom/convert?qty=2.5&from_uom={us['كجم']['id']}&to_uom={us['طن']['id']}",
                   headers=h).json()
    assert r["result"] == 0.003         # 2.5 kg -> 0.0025 t, rounded to 3dp
    bad = client.get(f"/api/uom/convert?qty=1&from_uom={us['كجم']['id']}&to_uom={us['حبة']['id']}",
                     headers=h)
    assert bad.status_code == 400       # cross-category


def test_product_uom_same_category_rule(client):
    h = login(client)
    us = units(client, h)
    ok = client.post("/api/products/", headers=h, json={
        "name": "تمر", "price": 30, "stock": 5,
        "uom_id": us["كجم"]["id"], "purchase_uom_id": us["طن"]["id"],
        "sales_uom_id": us["كجم"]["id"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["uom_name"] == "كجم"

    bad = client.post("/api/products/", headers=h, json={
        "name": "خطأ", "price": 1, "stock": 1,
        "uom_id": us["كجم"]["id"], "purchase_uom_id": us["حبة"]["id"]})  # different category
    assert bad.status_code == 400


def test_uom_isolation(client):
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'"); bayan = cur.fetchone()[0]
    cur.execute("SELECT id FROM tenants WHERE slug='uom_other'")
    row = cur.fetchone()
    other = row[0] if row else cur.execute(
        "INSERT INTO tenants(slug,name,is_active) VALUES('uom_other','UO',true) RETURNING id") or cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM uoms"); assert cur.fetchone()[0] >= 8
    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM uoms"); assert cur.fetchone()[0] == 0
    c.close()
