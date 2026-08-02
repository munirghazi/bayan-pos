"""Kitting feature tests: derived stock, nesting, cycles, and sale-time explosion.

Run: pytest -q tests/test_kitting.py
"""
import psycopg2
import pytest
from fastapi.testclient import TestClient

import main
from config import settings

PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")   # portable: read from .env


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, slug="bayan"):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": slug})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def test_kit_lifecycle(client):
    h = login(client)

    def create(**kw):
        r = client.post("/api/products", headers=h, json=kw)
        assert r.status_code == 200, r.text
        return r.json()

    def stock(pid):
        return client.get(f"/api/products/{pid}", headers=h).json()["stock"]

    rice = create(name="Rice", price=5, stock=100)
    oil = create(name="Oil", price=8, stock=50)
    dates = create(name="Dates", price=12, stock=30)

    # Kit with a fixed price; stock derived from components.
    basket = create(name="Basket", price=75, is_kit=True, components=[
        {"product_id": rice["id"], "quantity": 2},
        {"product_id": oil["id"], "quantity": 1},
        {"product_id": dates["id"], "quantity": 3},
    ])
    assert basket["is_kit"] is True
    assert basket["stock"] == 0
    assert basket["available_stock"] == 10          # min(100//2, 50//1, 30//3)
    assert {c["product_name"] for c in basket["components"]} == {"Rice", "Oil", "Dates"}

    # Nested kit: contains another kit.
    mega = create(name="Mega", price=200, is_kit=True, components=[
        {"product_id": basket["id"], "quantity": 2},
        {"product_id": rice["id"], "quantity": 1},
    ])
    assert mega["available_stock"] == 5             # min(10//2, 100//1)

    # Cycle rejection: Basket may not contain Mega (Mega already contains Basket).
    r = client.put(f"/api/products/{basket['id']}", headers=h, json={"components": [
        {"product_id": rice["id"], "quantity": 2},
        {"product_id": mega["id"], "quantity": 1},
    ]})
    assert r.status_code == 400 and "حلقة" in r.json()["detail"]

    # Self-reference rejection.
    r = client.put(f"/api/products/{basket['id']}", headers=h,
                   json={"components": [{"product_id": basket["id"], "quantity": 1}]})
    assert r.status_code == 400

    # Selling a kit uses its fixed price and deducts LEAF stock.
    r = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": basket["id"], "quantity": 3}], "payment_method": "cash"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 225.0               # 75 * 3, not sum of components
    assert stock(rice["id"]) == 94                  # 100 - 2*3
    assert stock(oil["id"]) == 47                   # 50 - 1*3
    assert stock(dates["id"]) == 21                 # 30 - 3*3

    # Oversell is blocked by the aggregated leaf check (dates limit).
    r = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": basket["id"], "quantity": 100}], "payment_method": "cash"})
    assert r.status_code == 400

    # Selling a nested kit explodes through both levels to the leaves.
    br, bo, bd = stock(rice["id"]), stock(oil["id"]), stock(dates["id"])
    r = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": mega["id"], "quantity": 1}], "payment_method": "cash"})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 200.0
    assert stock(rice["id"]) == br - 5              # 2(basket)*2 + 1 direct
    assert stock(oil["id"]) == bo - 2               # 2 * 1
    assert stock(dates["id"]) == bd - 6             # 2 * 3


def test_kit_components_tenant_isolation(client):
    # Ensure kit rows exist for 'bayan'.
    login(client)
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='bayan'")
    bayan = cur.fetchone()[0]

    cur.execute("SELECT id FROM tenants WHERE slug='kit_other'")
    row = cur.fetchone()
    if row:
        other = row[0]
    else:
        cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('kit_other','Other',true) RETURNING id")
        other = cur.fetchone()[0]

    cur.execute("SET app.current_tenant = %s", (str(bayan),))
    cur.execute("SELECT count(*) FROM kit_components")
    assert cur.fetchone()[0] > 0                     # bayan has kit rows

    cur.execute("SET app.current_tenant = %s", (str(other),))
    cur.execute("SELECT count(*) FROM kit_components")
    assert cur.fetchone()[0] == 0                     # other tenant sees none
    c.close()
