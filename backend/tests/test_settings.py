"""Per-tenant settings: CRUD, isolation, and per-tenant logo."""
import psycopg2
import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext

import main
from config import settings

PWD = CryptContext(schemes=["bcrypt"], deprecated="auto")
PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan", username="admin", password=PASSWORD):
    r = client.post("/api/auth/login",
                    json={"username": username, "password": password, "tenant": tenant})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def seed_other():
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug='set_other'")
    if cur.fetchone():
        c.close(); return
    cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES('set_other','Other Org',true) RETURNING id")
    tid = cur.fetchone()[0]
    cur.execute("SET app.current_tenant = %s", (str(tid),))
    cur.execute("INSERT INTO tenant_settings(tenant_id,seller_name,vat_rate,payment_methods,inventory_mode,fatoora_enabled_default) "
                "VALUES(%s,'Other Org',15,'cash','per_branch',false)", (tid,))
    cur.execute("INSERT INTO users(tenant_id,username,password_hash,full_name,role,is_active,must_change_password) "
                "VALUES(%s,'admin',%s,'A','admin',true,false)", (tid, PWD.hash(PASSWORD)))
    c.close()


def test_settings_crud_and_isolation(client):
    hb = login(client, "bayan")
    s = client.get("/api/settings/tenant", headers=hb).json()
    assert s["seller_name"] == "جمعية بيان"        # seeded from the tenant name

    r = client.put("/api/settings/tenant", headers=hb, json={
        "vat_number": "300000000000003", "city": "مكة المكرمة",
        "website": "https://bayanmakkah.org.sa"})
    assert r.status_code == 200, r.text
    s2 = client.get("/api/settings/tenant", headers=hb).json()
    assert s2["vat_number"] == "300000000000003" and s2["city"] == "مكة المكرمة"

    # a second tenant sees its OWN settings, unaffected by bayan's update
    seed_other()
    ho = login(client, "set_other")
    so = client.get("/api/settings/tenant", headers=ho).json()
    assert so["seller_name"] == "Other Org"
    assert so["vat_number"] != "300000000000003"


def test_per_tenant_logo(client):
    hb = login(client, "bayan")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    r = client.post("/api/settings/upload-logo", headers=hb,
                    files={"file": ("logo.png", png, "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("/uploads/tenant_")
    assert client.get("/api/settings/logo", headers=hb).json()["url"] == url
