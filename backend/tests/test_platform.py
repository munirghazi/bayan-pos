"""Release 2b: platform console — separate process, 2FA login, tenant management,
append-only audit log, RLS kept (tenants read one at a time)."""
import argparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
import manage
import platform_auth as pa
import platform_main
from config import settings
from database import SessionLocal, engine

H = {"X-Platform-Request": "1"}
ADMIN, ADMIN_PW = "ops", "PlatformPass123"


@pytest.fixture(scope="module")
def tenant_app():
    with TestClient(main.app) as c:          # runs the tenant bootstrap
        yield c


@pytest.fixture(scope="module")
def plat(tenant_app):
    db = SessionLocal()
    try:
        manage.cmd_platform_admin(db, argparse.Namespace(
            action="create", username=ADMIN, full_name="Ops", password=ADMIN_PW))
    finally:
        db.close()
    with TestClient(platform_main.app) as c:
        yield c


def _admin_row():
    with engine.begin() as c:
        return c.execute(text("SELECT * FROM platform_admins WHERE username=:u"), {"u": ADMIN}).mappings().first()


def _reset_step():
    with engine.begin() as c:
        c.execute(text("UPDATE platform_admins SET totp_last_step=NULL, failed_count=0, locked_until=NULL "
                       "WHERE username=:u"), {"u": ADMIN})


def sign_in(client):
    client.cookies.clear()
    _reset_step()
    r = client.post("/api/platform/auth/login", headers=H, json={"username": ADMIN, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    body = r.json()
    secret = body.get("secret") or pa.decrypt_secret(_admin_row()["totp_secret"])
    r = client.post("/api/platform/auth/mfa", headers=H,
                    json={"mfa_token": body["mfa_token"], "code": pa.totp_now(secret)})
    assert r.status_code == 200, r.text
    return secret


def tenant_login(client, slug, username, password):
    client.cookies.clear()
    return client.post("/api/auth/login", json={"username": username, "password": password, "tenant": slug})


# ------------------------------------------------------------------ separation + TOTP

def test_tenant_app_has_no_platform_api(tenant_app):
    assert tenant_app.post("/api/platform/auth/login", headers=H,
                           json={"username": ADMIN, "password": ADMIN_PW}).status_code in (404, 405)
    assert tenant_app.get("/api/platform/tenants").status_code == 404


def test_totp_rfc6238_vector_and_replay():
    # RFC 6238 test secret "12345678901234567890" (base32), T = 59 s -> 287082 (6 digits)
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert pa.totp_now(secret, at=59) == "287082"
    step = pa.verify_totp(secret, "287082", None, at=59)
    assert step == 1
    assert pa.verify_totp(secret, "287082", step, at=59) is None      # same code cannot be reused
    assert pa.verify_totp(secret, "000000", None, at=59) is None


def test_enrolment_then_login(plat):
    plat.cookies.clear()
    assert plat.post("/api/platform/auth/login", json={"username": ADMIN, "password": ADMIN_PW}).status_code == 403
    r = plat.post("/api/platform/auth/login", headers=H, json={"username": ADMIN, "password": ADMIN_PW})
    body = r.json()
    assert body["enroll"] is True and body["otpauth_uri"].startswith("otpauth://totp/")
    assert plat.post("/api/platform/auth/mfa", headers=H,
                     json={"mfa_token": body["mfa_token"], "code": "000000"}).status_code == 401
    assert _admin_row()["totp_enabled"] is False
    ok = plat.post("/api/platform/auth/mfa", headers=H,
                   json={"mfa_token": body["mfa_token"], "code": pa.totp_now(body["secret"])})
    assert ok.status_code == 200 and _admin_row()["totp_enabled"] is True
    assert plat.get("/api/platform/auth/me").json()["admin"]["username"] == ADMIN
    # next login: no new QR, the enrolled secret stays
    plat.cookies.clear()
    _reset_step()
    again = plat.post("/api/platform/auth/login", headers=H, json={"username": ADMIN, "password": ADMIN_PW}).json()
    assert again["enroll"] is False and "secret" not in again


def test_session_and_csrf_rules(plat, tenant_app):
    plat.cookies.clear()
    assert plat.get("/api/platform/tenants").status_code == 401
    # a tenant JWT is not a platform session
    tok = tenant_login(tenant_app, "bayan", "admin", settings.bootstrap_admin_password).json()["access_token"]
    plat.cookies.set(settings.platform_cookie_name, tok)
    assert plat.get("/api/platform/tenants").status_code == 401
    sign_in(plat)
    assert plat.get("/api/platform/tenants").status_code == 200
    # state-changing call without the custom header is refused
    assert plat.post("/api/platform/tenants", json={"slug": "x-y", "name": "x"}).status_code == 403


def test_lockout_after_failed_attempts(plat):
    plat.cookies.clear()
    _reset_step()
    for _ in range(settings.platform_max_login_attempts):
        assert plat.post("/api/platform/auth/login", headers=H,
                         json={"username": ADMIN, "password": "wrong-password"}).status_code == 401
    r = plat.post("/api/platform/auth/login", headers=H, json={"username": ADMIN, "password": ADMIN_PW})
    assert r.status_code == 429
    db = SessionLocal()
    try:
        manage.cmd_platform_admin(db, argparse.Namespace(action="unlock", username=ADMIN, full_name=None, password=None))
    finally:
        db.close()
    sign_in(plat)


# ------------------------------------------------------------------ tenants

NEW = {"slug": "charity-two", "name": "جمعية الاختبار الثانية", "name_en": "Second Test Association",
       "entity_type": "nonprofit_association", "license_number": "2002", "unified_number": "7000000002",
       "vat_enabled": False, "sales_enabled": True, "donations_enabled": True,
       "admin_username": "admin2", "branch_name": "الفرع الرئيسي"}


def test_wizard_creates_tenant_with_admin_branch_units(plat, tenant_app):
    sign_in(plat)
    bad = plat.post("/api/platform/tenants", headers=H, json={**NEW, "slug": "Bad Slug"})
    assert bad.status_code == 400
    shop = plat.post("/api/platform/tenants", headers=H,
                     json={**NEW, "slug": "shop-x", "entity_type": "company", "cr_number": "1010"})
    assert shop.status_code == 400 and "غير الربحية" in shop.json()["detail"]     # donations need non-profit
    r = plat.post("/api/platform/tenants", headers=H, json=NEW)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["tenant"]["business_type"] == "mixed" and out["tenant"]["missing"] == []
    assert plat.post("/api/platform/tenants", headers=H, json=NEW).status_code == 409

    login = tenant_login(tenant_app, "charity-two", "admin2", out["temp_password"])
    assert login.status_code == 200 and login.json()["user"]["must_change_password"] is True
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    branches = tenant_app.get("/api/locations/", headers=h).json()
    assert branches and branches[0]["code"] == "B01"
    assert len(tenant_app.get("/api/uom/units", headers=h).json()) > 0

    detail = plat.get(f"/api/platform/tenants/{out['tenant']['id']}").json()
    assert detail["stats"]["users"] == 1 and detail["stats"]["registers"] == 1
    assert detail["can_delete"] is True and detail["branches"][0]["code"] == "B01"
    lst = plat.get("/api/platform/tenants").json()
    assert {t["slug"] for t in lst} >= {"bayan", "charity-two"}


def _tid(plat, slug):
    return next(t["id"] for t in plat.get("/api/platform/tenants").json() if t["slug"] == slug)


def test_identity_and_capabilities(plat, tenant_app):
    sign_in(plat)
    tid = _tid(plat, "charity-two")
    assert plat.put(f"/api/platform/tenants/{tid}/identity", headers=H,
                    json={"vat_enabled": True, "vat_number": "123"}).status_code == 400
    assert plat.put(f"/api/platform/tenants/{tid}/identity", headers=H,
                    json={"vat_enabled": True}).status_code == 400       # VAT number required
    ok = plat.put(f"/api/platform/tenants/{tid}/identity", headers=H,
                  json={"vat_enabled": True, "vat_number": "300000000000003", "vat_rate": 15})
    assert ok.status_code == 200 and ok.json()["vat_number"] == "300000000000003"
    # becoming a company switches donations off
    co = plat.put(f"/api/platform/tenants/{tid}/identity", headers=H,
                  json={"entity_type": "company", "cr_number": "4030000000"}).json()
    assert co["donations_enabled"] is False and co["business_type"] == "trade"
    assert plat.put(f"/api/platform/tenants/{tid}/capabilities", headers=H,
                    json={"donations_enabled": True}).status_code == 400
    assert plat.put(f"/api/platform/tenants/{tid}/capabilities", headers=H,
                    json={"sales_enabled": False}).status_code == 400   # nothing left enabled
    caps = plat.put(f"/api/platform/tenants/{tid}/capabilities", headers=H,
                    json={"purchasing_enabled": False, "verification_status": "pending"}).json()
    assert caps["purchasing_enabled"] is False and caps["verification_status"] == "pending"
    # the tenant sees the platform-set identity
    pw = plat.post(f"/api/platform/tenants/{tid}/users/"
                   f"{plat.get(f'/api/platform/tenants/{tid}').json()['users'][0]['id']}/reset-password",
                   headers=H).json()["temp_password"]
    h = {"Authorization": f"Bearer {tenant_login(tenant_app, 'charity-two', 'admin2', pw).json()['access_token']}"}
    s = tenant_app.get("/api/settings/tenant", headers=h).json()
    assert s["entity_type"] == "company" and s["vat_number"] == "300000000000003"


def test_suspend_ends_sessions_and_blocks_login(plat, tenant_app):
    sign_in(plat)
    tid = _tid(plat, "charity-two")
    users = plat.get(f"/api/platform/tenants/{tid}").json()["users"]
    pw = plat.post(f"/api/platform/tenants/{tid}/users/{users[0]['id']}/reset-password", headers=H).json()["temp_password"]
    tok = tenant_login(tenant_app, "charity-two", "admin2", pw).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert tenant_app.get("/api/auth/me", headers=h).status_code == 200
    assert plat.post(f"/api/platform/tenants/{tid}/suspend", headers=H, json={}).status_code == 400   # reason
    assert plat.post(f"/api/platform/tenants/{tid}/suspend", headers=H, json={"reason": "اختبار"}).status_code == 200
    tenant_app.cookies.clear()
    assert tenant_app.get("/api/auth/me", headers=h).status_code == 401
    assert tenant_login(tenant_app, "charity-two", "admin2", pw).status_code == 400
    plat.post(f"/api/platform/tenants/{tid}/activate", headers=H)
    tenant_app.cookies.clear()
    assert tenant_app.get("/api/auth/me", headers=h).status_code == 200


def test_reset_password_replaces_old_one(plat, tenant_app):
    sign_in(plat)
    tid = _tid(plat, "charity-two")
    uid = plat.get(f"/api/platform/tenants/{tid}").json()["users"][0]["id"]
    first = plat.post(f"/api/platform/tenants/{tid}/users/{uid}/reset-password", headers=H).json()["temp_password"]
    second = plat.post(f"/api/platform/tenants/{tid}/users/{uid}/reset-password", headers=H).json()["temp_password"]
    assert tenant_login(tenant_app, "charity-two", "admin2", first).status_code == 401
    assert tenant_login(tenant_app, "charity-two", "admin2", second).status_code == 200


def test_delete_rules(plat, monkeypatch):
    sign_in(plat)
    tid = _tid(plat, "charity-two")
    assert plat.request("DELETE", f"/api/platform/tenants/{tid}", headers=H,
                        json={"confirm_slug": "wrong"}).status_code == 400
    import routers.platform as rp
    real = rp._stats
    monkeypatch.setattr(rp, "_stats", lambda db, t: {**real(db, t), "documents": 3})
    blocked = plat.request("DELETE", f"/api/platform/tenants/{tid}", headers=H, json={"confirm_slug": "charity-two"})
    assert blocked.status_code == 409 and "6 سنوات" in blocked.json()["detail"]
    monkeypatch.setattr(rp, "_stats", real)
    ok = plat.request("DELETE", f"/api/platform/tenants/{tid}", headers=H, json={"confirm_slug": "charity-two"})
    assert ok.status_code == 200
    assert "charity-two" not in {t["slug"] for t in plat.get("/api/platform/tenants").json()}
    # the trail of the deleted tenant survives
    trail = plat.get("/api/platform/audit", params={"tenant": "charity-two"}).json()
    assert {"tenant_created", "tenant_suspended", "tenant_deleted"} <= {a["action"] for a in trail}


def test_tenant_with_documents_cannot_be_deleted(plat):
    sign_in(plat)
    bayan = next(t for t in plat.get("/api/platform/tenants").json() if t["slug"] == "bayan")
    if bayan["stats"]["documents"] == 0:
        pytest.skip("no documents in this test run")
    r = plat.request("DELETE", f"/api/platform/tenants/{bayan['id']}", headers=H, json={"confirm_slug": "bayan"})
    assert r.status_code == 409


def test_audit_is_append_only_and_records_logins(plat):
    sign_in(plat)
    actions = {a["action"] for a in plat.get("/api/platform/audit").json()}
    assert {"login", "login_failed", "login_locked", "mfa_enrolled"} <= actions
    for sql in ("UPDATE platform_audit_log SET action='x'", "DELETE FROM platform_audit_log"):
        with pytest.raises(Exception):
            with engine.begin() as c:
                c.execute(text(sql))


def test_password_change_needs_totp_and_ends_session(plat):
    secret = sign_in(plat)
    with engine.begin() as c:     # the sign-in code's step is used; allow the current step once more
        c.execute(text("UPDATE platform_admins SET totp_last_step = totp_last_step - 2 WHERE username=:u"), {"u": ADMIN})
    assert plat.post("/api/platform/auth/change-password", headers=H, json={
        "current_password": ADMIN_PW, "new_password": "NewPlatform456", "code": "000000"}).status_code == 400
    r = plat.post("/api/platform/auth/change-password", headers=H, json={
        "current_password": ADMIN_PW, "new_password": "NewPlatform456", "code": pa.totp_now(secret)})
    assert r.status_code == 200
    assert plat.get("/api/platform/auth/me").status_code == 401
    # restore for any later runs in this session
    db = SessionLocal()
    try:
        manage.cmd_platform_admin(db, argparse.Namespace(
            action="set-password", username=ADMIN, full_name=None, password=ADMIN_PW))
    finally:
        db.close()
