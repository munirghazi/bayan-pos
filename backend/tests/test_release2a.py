"""Release 2a: organization type + registration numbers (platform-controlled),
national address (proof order, Arabic + English), donations for non-profits only."""
import argparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
import manage
from config import settings
from database import engine, SessionLocal

PASSWORD = settings.bootstrap_admin_password


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _tenant(**cols):
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    with engine.begin() as c:
        c.execute(text(f"UPDATE tenants SET {sets} WHERE slug = 'bayan'"), cols)


@pytest.fixture(autouse=True)
def _restore():
    yield
    _tenant(entity_type="nonprofit_association", donations_enabled=True, unified_number=None, name_en=None)


def _identity_args(**kw):
    base = dict(slug="bayan", type=None, name=None, name_en=None, unified=None, cr=None,
                license=None, freelance=None, vat=None, vat_enabled=None, vat_rate=None)
    base.update(kw)
    return argparse.Namespace(**base)


# ------------------------------------------------------------------ identity

def test_settings_expose_entity_and_default_thanks(client):
    h = login(client)
    s = client.get("/api/settings/tenant", headers=h).json()
    assert s["entity_type"] == "nonprofit_association"
    assert s["entity_type_label"] == "جمعية أهلية" and s["entity_group"] == "nonprofit"
    assert s["primary_registration"] == "license_number"
    assert s["default_thanks"] == "جزاكم الله خيراً"
    caps = client.get("/api/auth/capabilities", headers=h).json()
    assert caps["entity_group"] == "nonprofit"


def test_identity_is_read_only_for_the_tenant(client):
    h = login(client)
    cur = client.get("/api/settings/tenant", headers=h).json()
    for field, value in (("vat_number", "399999999999993"), ("seller_name", "اسم آخر"), ("vat_rate", 5)):
        r = client.put("/api/settings/tenant", headers=h, json={field: value})
        assert r.status_code == 403, (field, r.text)
    # sending the unchanged values (as an old screen would) is harmless
    ok = client.put("/api/settings/tenant", headers=h, json={
        "seller_name": cur["seller_name"], "vat_number": cur["vat_number"],
        "vat_rate": cur["vat_rate"], "city": cur["city"]})
    assert ok.status_code == 200, ok.text


def test_manage_identity_command():
    db = SessionLocal()
    try:
        assert manage.cmd_identity(db, _identity_args(unified="12345")) == 1          # bad format
        assert manage.cmd_identity(db, _identity_args(type="nope")) == 1
        assert manage.cmd_identity(db, _identity_args(unified="7012345678", name_en="Bayan Association")) == 0
    finally:
        db.close()
    with engine.begin() as c:
        row = c.execute(text("SELECT unified_number, name_en FROM tenants WHERE slug='bayan'")).one()
    assert row == ("7012345678", "Bayan Association")


def test_unified_number_constraint_in_db():
    with pytest.raises(Exception):
        _tenant(unified_number="1234567890")


# ------------------------------------------------------------------ donations by type

def test_commercial_types_cannot_take_donations(client):
    h = login(client)
    db = SessionLocal()
    try:
        assert manage.cmd_identity(db, _identity_args(type="company")) == 0
    finally:
        db.close()
    with engine.begin() as c:
        assert c.execute(text("SELECT donations_enabled FROM tenants WHERE slug='bayan'")).scalar() is False
    caps = client.get("/api/auth/capabilities", headers=h).json()
    assert caps["donations_enabled"] is False and caps["entity_group"] == "commercial"

    # even if someone switches the flag back on, a company still can't receive donations
    _tenant(donations_enabled=True)
    assert client.post("/api/donations/", headers=h,
                       json={"amount": 10, "payment_method": "card", "card_ref": "X"}).status_code == 403
    dash = client.get("/api/reports/dashboard", headers=h).json()
    assert dash["donations_enabled"] is False
    assert client.get("/api/settings/tenant", headers=h).json()["default_thanks"] == "شكراً لتسوقكم معنا"


# ------------------------------------------------------------------ national address

def test_national_address_order_formats_and_english(client):
    h = login(client)
    r = client.put("/api/settings/tenant", headers=h, json={
        "short_address": "jbra 6522", "building_number": "6522", "street_name": "معاذ التميمي",
        "street_name_en": "Muath Al Tamimi", "additional_number": "4816", "district": "حي الرويس",
        "district_en": "Ar Ruwais Dist.", "postal_code": "23214", "city": "جدة", "city_en": "JEDDAH",
        "country_en": "Kingdom of Saudi Arabia", "address_proof_number": "1089560005",
        "address_proof_expiry": "2027-01-09", "show_en_address": True})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["short_address"] == "JBRA6522" and s["street_name_en"] == "Muath Al Tamimi"
    assert s["address_proof_expiry"] == "2027-01-09" and s["show_en_address"] is True

    for bad in ({"short_address": "AB12"}, {"building_number": "12"},
                {"additional_number": "48"}, {"postal_code": "2321"}):
        assert client.put("/api/settings/tenant", headers=h, json=bad).status_code == 400, bad

    # the invoice keeps the identity + bilingual address as issued
    pid = client.post("/api/products/", headers=h, json={"name": "عنوان", "price": 10, "stock": 5}).json()["id"]
    _tenant(unified_number="7012345678", name_en="Bayan Association")
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 1}], "payment_method": "cash"}).json()
    seller = sale["seller"]
    assert seller["short_address"] == "JBRA6522" and seller["secondary_number"] == "4816"
    assert seller["city_en"] == "JEDDAH" and seller["show_en_address"] is True
    assert seller["unified_number"] == "7012345678" and seller["name_en"] == "Bayan Association"
    assert seller["entity_type_label"] == "جمعية أهلية" and seller["thanks"] == "جزاكم الله خيراً"
    client.put("/api/settings/tenant", headers=h, json={"show_en_address": False})


def test_custom_thanks_line(client):
    h = login(client)
    client.put("/api/settings/tenant", headers=h, json={"receipt_thanks": "نسعد بخدمتكم"})
    pid = client.post("/api/products/", headers=h, json={"name": "شكر", "price": 5, "stock": 5}).json()["id"]
    sale = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 1}], "payment_method": "cash"}).json()
    assert sale["seller"]["thanks"] == "نسعد بخدمتكم"
    client.put("/api/settings/tenant", headers=h, json={"receipt_thanks": ""})
