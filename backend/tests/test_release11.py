"""Release 1.1: split payment, transfer proofs, drafts with stock reservation,
refund method + cash refunds in the Z-report, invoice search, default units."""
import secrets

import psycopg2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from config import settings
from database import engine

PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")
PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 64
PDF = b"%PDF-1.4\n%test\n"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _tid():
    with engine.begin() as c:
        return c.execute(text("SELECT id FROM tenants WHERE slug='bayan'")).scalar()


def _sql(stmt, params=()):
    c = psycopg2.connect(RAW_DSN); c.autocommit = True
    cur = c.cursor(); cur.execute("SET app.current_tenant = %s", (str(_tid()),))
    cur.execute(stmt, params)
    out = cur.fetchall() if cur.description else None
    c.close()
    return out


def _product(client, h, price=115, stock=100, name=None):
    return client.post("/api/products/", headers=h, json={
        "name": name or ("ص-" + secrets.token_hex(3)), "price": price, "stock": stock}).json()["id"]


def _proof(client, h, data=PNG, name="t.png"):
    r = client.post("/api/payment-proofs/", headers=h, files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _sale(client, h, pid, payments, qty=1, **extra):
    return client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": qty}], "payments": payments, **extra})


def _stock(client, h, pid):
    return next(p for p in client.get("/api/products/", headers=h).json() if p["id"] == pid)["stock"]


# ------------------------------------------------------------------ split payment

def test_split_payment_with_cash_change(client):
    h = login(client)
    pid = _product(client, h, 115)
    r = _sale(client, h, pid, [{"method": "card", "amount": 50, "card_ref": "A1"},
                               {"method": "cash", "amount": 100}])
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["payment_method"] == "mixed" and s["change_given"] == 35.0
    pays = {p["method"]: p for p in s["payments"]}
    assert pays["card"]["amount"] == 50.0
    assert pays["cash"]["amount"] == 65.0 and pays["cash"]["tendered"] == 100.0


def test_only_cash_may_overpay(client):
    h = login(client)
    pid = _product(client, h, 115)
    over_card = _sale(client, h, pid, [{"method": "card", "amount": 120, "card_ref": "A"}])
    assert over_card.status_code == 400
    over_transfer = _sale(client, h, pid, [{"method": "transfer", "amount": 120,
                                            "proof_id": _proof(client, h)}])
    assert over_transfer.status_code == 400
    under = _sale(client, h, pid, [{"method": "cash", "amount": 100}])
    assert under.status_code == 400
    useless_cash = _sale(client, h, pid, [{"method": "card", "amount": 115, "card_ref": "A"},
                                          {"method": "cash", "amount": 10}])
    assert useless_cash.status_code == 400
    exact = _sale(client, h, pid, [{"method": "cash", "amount": 200}])
    assert exact.status_code == 200 and exact.json()["change_given"] == 85.0


# ------------------------------------------------------------------ transfer proofs

def test_transfer_needs_a_proof_and_a_proof_is_single_use(client):
    h = login(client)
    pid = _product(client, h, 50)
    no_proof = _sale(client, h, pid, [{"method": "transfer", "amount": 50}])
    assert no_proof.status_code == 400
    pr = _proof(client, h, PDF, "receipt.pdf")
    ok = _sale(client, h, pid, [{"method": "transfer", "amount": 50, "proof_id": pr}])
    assert ok.status_code == 200, ok.text
    again = _sale(client, h, pid, [{"method": "transfer", "amount": 50, "proof_id": pr}])
    assert again.status_code == 400

    meta = client.get(f"/api/payment-proofs/{pr}", headers=h).json()
    assert meta["used"] is True and meta["used_ref"] == ok.json()["invoice_number"]
    f = client.get(f"/api/payment-proofs/{pr}/file", headers=h)
    assert f.status_code == 200 and f.content == PDF
    assert f.headers["content-type"].startswith("application/pdf")
    # not reachable as a public static file
    assert client.get("/uploads/" + str(pr)).status_code == 404


def test_proof_upload_rejects_non_image_or_pdf(client):
    h = login(client)
    r = client.post("/api/payment-proofs/", headers=h, files={"file": ("x.png", b"hello world", "image/png")})
    assert r.status_code == 400


def test_proof_requirement_can_be_switched_off(client):
    h = login(client)
    pid = _product(client, h, 20)
    _sql("UPDATE tenant_settings SET require_transfer_proof = false")
    try:
        r = _sale(client, h, pid, [{"method": "transfer", "amount": 20}])
        assert r.status_code == 200, r.text
    finally:
        _sql("UPDATE tenant_settings SET require_transfer_proof = true")


# ------------------------------------------------------------------ drafts

def test_draft_reserves_stock_and_takes_no_number_until_issued(client):
    h = login(client)
    pid = _product(client, h, 10, stock=3)
    before = _sale(client, h, _product(client, h, 1), [{"method": "cash", "amount": 1}]).json()["invoice_number"]

    payload = {"items": [{"product_id": pid, "quantity": 2}],
               "payments": [{"method": "transfer", "amount": 20}]}
    # an issue attempt without proof is refused …
    assert client.post("/api/sales/", headers=h, json=payload).status_code == 400
    # … but it can be parked as a draft
    d = client.post("/api/drafts/sale", headers=h, json=payload)
    assert d.status_code == 200, d.text
    draft = d.json()
    assert draft["status"] == "open" and draft["total"] == 20.0
    assert _stock(client, h, pid) == 3            # nothing deducted yet

    # 2 of 3 are reserved: selling 2 more must fail, selling 1 works
    assert _sale(client, h, pid, [{"method": "cash", "amount": 20}], qty=2).status_code == 400
    one = _sale(client, h, pid, [{"method": "cash", "amount": 10}], qty=1)
    assert one.status_code == 200, one.text

    issued = client.post(f"/api/drafts/{draft['id']}/issue", headers=h, json={
        "payments": [{"method": "transfer", "amount": 20, "proof_id": _proof(client, h)}]})
    assert issued.status_code == 200, issued.text
    inv_no = issued.json()["sale"]["invoice_number"]
    assert issued.json()["draft"]["status"] == "issued" and issued.json()["draft"]["issued_ref"] == inv_no
    assert _stock(client, h, pid) == 0
    # numbers stayed gap-free: before, the cash sale of 1, then the draft's invoice
    seq = lambda n: int(n.rsplit("-", 1)[1])
    assert seq(inv_no) == seq(one.json()["invoice_number"]) + 1 == seq(before) + 2
    # an issued draft can't be issued again
    assert client.post(f"/api/drafts/{draft['id']}/issue", headers=h, json={}).status_code == 400


def test_cancelled_and_expired_drafts_release_stock(client):
    h = login(client)
    pid = _product(client, h, 10, stock=2)
    payload = {"items": [{"product_id": pid, "quantity": 2}], "payments": [{"method": "transfer", "amount": 20}]}
    d1 = client.post("/api/drafts/sale", headers=h, json=payload).json()
    assert _sale(client, h, pid, [{"method": "cash", "amount": 10}]).status_code == 400
    assert client.post(f"/api/drafts/{d1['id']}/cancel", headers=h, json={"reason": "عدل العميل"}).json()["status"] == "cancelled"

    d2 = client.post("/api/drafts/sale", headers=h, json=payload).json()
    _sql("UPDATE pos_drafts SET created_at = now() - interval '2 days' WHERE id = %s", (d2["id"],))
    open_ids = [x["id"] for x in client.get("/api/drafts/", headers=h).json()]
    assert d2["id"] not in open_ids
    assert _sale(client, h, pid, [{"method": "cash", "amount": 20}], qty=2).status_code == 200


def test_donation_draft_then_issue_with_proof(client):
    h = login(client)
    d = client.post("/api/drafts/donation", headers=h,
                    json={"amount": 40, "payment_method": "transfer", "donor_name": "متبرع"})
    assert d.status_code == 200, d.text
    r = client.post(f"/api/drafts/{d.json()['id']}/issue", headers=h, json={"proof_id": _proof(client, h)})
    assert r.status_code == 200, r.text
    don = r.json()["donation"]
    assert don["receipt_number"].split("-")[1] == "DON" and don["proof_id"]


# ------------------------------------------------------------------ refunds

def test_refund_method_and_cash_refunds_in_zreport(client):
    h = login(client)
    loc = client.get("/api/locations/", headers=h).json()[0]["id"]
    rid = client.post("/api/registers/", headers=h,
                      json={"name": "ص-" + secrets.token_hex(3), "location_id": loc}).json()["id"]
    pid = _product(client, h, 100)
    s = _sale(client, h, pid, [{"method": "card", "amount": 100, "card_ref": "C9"}], qty=1,
              register_id=rid).json()
    s2 = _sale(client, h, pid, [{"method": "cash", "amount": 100}], qty=1, register_id=rid).json()

    bad = client.post("/api/returns/", headers=h, json={
        "invoice_number": s["invoice_number"], "reason": "x", "refund_method": "transfer",
        "items": [{"product_id": pid, "quantity": 1}]})
    assert bad.status_code == 400                      # not used on the invoice, not cash
    ok = client.post("/api/returns/", headers=h, json={
        "invoice_number": s["invoice_number"], "reason": "x", "refund_method": "cash",
        "items": [{"product_id": pid, "quantity": 1}]})
    assert ok.status_code == 200 and ok.json()["refund_method"] == "cash"

    z = client.get(f"/api/registers/{rid}/z-report", headers=h).json()
    assert z["by_method"]["card"] == 100.0 and z["by_method"]["cash"] == 100.0
    assert z["cash_refunds"] == 100.0 and z["expected_cash"] == 0.0

    ra = client.get(f"/api/returns/invoice/{s2['invoice_number']}", headers=h).json()
    assert ra["refund_methods"] == ["cash"]


# ------------------------------------------------------------------ search

def test_invoice_search_filters(client):
    h = login(client)
    phone = "+9665" + str(secrets.randbelow(10**8)).zfill(8)
    cust = client.post("/api/customers/", headers=h, json={"name": "عميل بحث", "phone": phone}).json()
    pid = _product(client, h, 33)
    s = _sale(client, h, pid, [{"method": "card", "amount": 33, "card_ref": "REF-777"}],
              customer_id=cust["id"]).json()

    by_no = client.get("/api/sales/search", headers=h, params={"q": s["invoice_number"][-6:]}).json()
    assert any(r["id"] == s["id"] for r in by_no["rows"])
    by_phone = client.get("/api/sales/search", headers=h, params={"customer": phone[-8:]}).json()
    assert [r["id"] for r in by_phone["rows"]] == [s["id"]]
    by_ref = client.get("/api/sales/search", headers=h, params={"q": "REF-777"}).json()
    assert any(r["id"] == s["id"] for r in by_ref["rows"])
    by_amount = client.get("/api/sales/search", headers=h,
                           params={"amount_min": 33, "amount_max": 33, "method": "card"}).json()
    assert any(r["id"] == s["id"] for r in by_amount["rows"])
    nothing = client.get("/api/sales/search", headers=h, params={"date_from": "2000-01-01",
                                                                  "date_to": "2000-01-02"}).json()
    assert nothing["count"] == 0


# ------------------------------------------------------------------ units

def test_every_tenant_gets_default_units(client):
    c = psycopg2.connect(RAW_DSN); c.autocommit = True; cur = c.cursor()
    slug = "u" + secrets.token_hex(3)
    cur.execute("INSERT INTO tenants(slug,name,is_active) VALUES(%s,'وحدات',true) RETURNING id", (slug,))
    tid = cur.fetchone()[0]
    c.close()
    with TestClient(main.app):        # startup seeds every tenant
        pass
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)})
        n = conn.execute(text("SELECT count(*) FROM uoms")).scalar()
        b = conn.execute(text("SELECT count(*) FROM locations")).scalar()
    assert n > 0 and b == 1
