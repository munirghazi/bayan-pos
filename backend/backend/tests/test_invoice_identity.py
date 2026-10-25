"""Invoice identity is sourced from backend settings (with onboarding fallback),
and a complete national address is REQUIRED for trade/mixed tenants to invoice."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
import main
from config import settings as cfg
from database import engine

PASSWORD = cfg.bootstrap_admin_password


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _tid():
    with engine.begin() as c:
        return c.execute(text("SELECT id FROM tenants WHERE slug='bayan'")).scalar()


def _restore_identity(tid):
    """Reset the demo tenant to a complete, invoice-ready identity (bootstrap values)."""
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)})
        c.execute(text(
            "UPDATE tenant_settings SET "
            "seller_name = (SELECT name FROM tenants WHERE id = :t), "
            "vat_number='300000000000003', building_number='1234', "
            "street_name='طريق الملك عبدالعزيز', district='النسيم', city='مكة المكرمة', "
            "postal_code='24231', additional_number='9013', country='SA' "
            "WHERE tenant_id = :t"), {"t": tid})


@pytest.fixture(autouse=True)
def _identity_guard():
    yield
    _restore_identity(_tid())   # never leave tenant_settings incomplete for other modules


def test_settings_falls_back_to_onboarding_identity(client):
    h = login(client)
    tid = _tid()
    with engine.begin() as c:
        orig = c.execute(text("SELECT name, vat_number, national_address FROM tenants WHERE id=:i"),
                         {"i": tid}).one()
    try:
        with engine.begin() as c:
            c.execute(text("UPDATE tenants SET name='مؤسسة الاختبار', vat_number='300123456700003', "
                           "national_address='RESA2929' WHERE id=:i"), {"i": tid})
            c.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)})
            c.execute(text("UPDATE tenant_settings SET seller_name=NULL, vat_number=NULL, "
                           "national_address=NULL WHERE tenant_id=:t"), {"t": tid})
        d = client.get("/api/settings/tenant", headers=h).json()
        assert d["seller_name"] == "مؤسسة الاختبار"
        assert d["vat_number"] == "300123456700003"
        assert d["national_address"] == "RESA2929"
    finally:
        with engine.begin() as c:
            c.execute(text("UPDATE tenants SET name=:n, vat_number=:v, national_address=:na WHERE id=:i"),
                      {"n": orig.name, "v": orig.vat_number, "na": orig.national_address, "i": tid})


def test_structured_address_round_trips(client):
    h = login(client)
    client.put("/api/settings/tenant", headers=h, json={
        "building_number": "4020", "street_name": "طريق الأمير سلطان",
        "district": "الروضة", "city": "جدة", "postal_code": "23434",
        "additional_number": "7788", "region": "مكة المكرمة"})
    d = client.get("/api/settings/tenant", headers=h).json()
    assert d["building_number"] == "4020" and d["postal_code"] == "23434"
    assert d["district"] == "الروضة" and d["street_name"] == "طريق الأمير سلطان"


def test_invoice_blocked_until_address_complete(client):
    h = login(client)
    tid = _tid()
    # wipe the address -> sale (invoice) must be refused with a clear message
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)})
        c.execute(text("UPDATE tenant_settings SET building_number=NULL, street_name=NULL, "
                       "district=NULL, postal_code=NULL WHERE tenant_id=:t"), {"t": tid})
        c.execute(text("UPDATE tenants SET vat_number=NULL WHERE id=:t"), {"t": tid})
    r = client.post("/api/sales/", headers=h, json={"items": [], "payment_method": "cash"})
    assert r.status_code == 400
    assert "العنوان الوطني" in r.json()["detail"]
    # once restored (autouse guard also restores), a sale is no longer blocked on identity
    _restore_identity(tid)
    r2 = client.post("/api/sales/", headers=h, json={"items": [], "payment_method": "cash"})
    # empty items -> 400 "add a product", NOT the identity error
    assert r2.status_code == 400 and "العنوان الوطني" not in r2.json()["detail"]
