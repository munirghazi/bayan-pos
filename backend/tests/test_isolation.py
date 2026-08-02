"""Proves tenant isolation at two layers:
  A) API layer   — a tenant's token only ever sees its own rows.
  B) Database RLS — even a raw connection that "forgets" to filter sees only
     the pinned tenant, cannot write across tenants, and sees nothing when no
     tenant is set (fail-closed).

Run:  pytest -q tests/test_isolation.py
"""
import psycopg2
import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

import main
from config import settings

PWD = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD = settings.bootstrap_admin_password  # same pw reused for the 2nd tenant
RAW_DSN = settings.database_url.replace("+psycopg2", "")   # portable: read from .env


def raw():
    c = psycopg2.connect(RAW_DSN)
    c.autocommit = True
    return c


def seed_other_tenant():
    """Create a 2nd tenant 'other' with its own admin, via a raw app connection."""
    c = raw(); cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='other'")
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('other','Other',true) RETURNING id")
    other_id = cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(other_id),))
    cur.execute(
        "INSERT INTO tenant_settings(tenant_id,seller_name,vat_rate,inventory_mode,"
        "fatoora_enabled_default,payment_methods) VALUES(%s,'Other',15,'per_branch',false,'cash')",
        (other_id,),
    )
    cur.execute(
        "INSERT INTO users(tenant_id,username,password_hash,full_name,role,is_active,"
        "must_change_password) VALUES(%s,'admin',%s,'Other Admin','admin',true,false)",
        (other_id, PWD.hash(PASSWORD)),
    )
    c.close()
    return other_id


def tenant_id(slug):
    c = raw(); cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug=%s", (slug,))
    tid = cur.fetchone()[0]; c.close(); return tid


def login(client, slug):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": slug})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()   # avoid the httpOnly cookie overriding the Bearer header
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:   # lifespan seeds tenant 'bayan' + admin
        seed_other_tenant()
        yield c


def test_api_layer_isolation(client):
    hb = login(client, "bayan")
    ho = login(client, "other")
    # each tenant creates a product
    assert client.post("/api/products", headers=hb,
                       json={"name": "Bayan-Widget", "price": 10}).status_code == 200
    assert client.post("/api/products", headers=ho,
                       json={"name": "Other-Widget", "price": 20}).status_code == 200

    names_b = {p["name"] for p in client.get("/api/products", headers=hb).json()}
    names_o = {p["name"] for p in client.get("/api/products", headers=ho).json()}

    assert "Bayan-Widget" in names_b and "Other-Widget" not in names_b
    assert "Other-Widget" in names_o and "Bayan-Widget" not in names_o


def test_db_rls_read_isolation(client):
    b, o = tenant_id("bayan"), tenant_id("other")
    c = raw(); cur = c.cursor()

    cur.execute("SET app.current_tenant = %s", (str(b),))
    cur.execute("SELECT count(*) FROM products WHERE name='Other-Widget'")
    assert cur.fetchone()[0] == 0                      # cannot see other tenant
    cur.execute("SELECT count(*) FROM products WHERE name='Bayan-Widget'")
    assert cur.fetchone()[0] == 1

    cur.execute("SET app.current_tenant = %s", (str(o),))
    cur.execute("SELECT count(*) FROM products WHERE name='Bayan-Widget'")
    assert cur.fetchone()[0] == 0
    c.close()


def test_db_rls_blocks_cross_tenant_write(client):
    b, o = tenant_id("bayan"), tenant_id("other")
    c = raw(); cur = c.cursor()
    cur.execute("SET app.current_tenant = %s", (str(b),))
    # try to plant a row belonging to tenant 'other' while acting as 'bayan'
    with pytest.raises(psycopg2.Error) as ei:
        cur.execute("INSERT INTO products(tenant_id,name,price,stock,is_active) "
                    "VALUES(%s,'evil',1,0,true)", (o,))
    assert "row-level security" in str(ei.value).lower()
    c.close()


def test_db_rls_fail_closed_without_tenant(client):
    c = raw(); cur = c.cursor()
    cur.execute("RESET app.current_tenant")
    cur.execute("SELECT count(*) FROM products")
    assert cur.fetchone()[0] == 0                      # no tenant set => zero rows
    c.close()
