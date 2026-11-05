"""ZATCA Release 1: per-branch numbering, VAT/seller snapshot, QR, hash chain,
immutability, credit notes, donation receipts and the donations flag."""
import base64
import threading

import psycopg2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import main
from config import settings
from database import engine

PASSWORD = settings.bootstrap_admin_password
RAW_DSN = settings.database_url.replace("+psycopg2", "")


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def login(client, tenant="bayan"):
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": PASSWORD, "tenant": tenant})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


def _tid():
    with engine.begin() as c:
        return c.execute(text("SELECT id FROM tenants WHERE slug='bayan'")).scalar()


def _raw():
    c = psycopg2.connect(RAW_DSN)
    c.autocommit = True
    cur = c.cursor()
    cur.execute("SET app.current_tenant = %s", (str(_tid()),))
    return c, cur


def _tenant_flags(**flags):
    sets = ", ".join(f"{k} = {str(bool(v)).lower()}" for k, v in flags.items())
    with engine.begin() as c:
        c.execute(text(f"UPDATE tenants SET {sets} WHERE slug = 'bayan'"))


def _set_rate(rate):
    c, cur = _raw()
    cur.execute("UPDATE tenant_settings SET vat_rate = %s", (rate,))
    c.close()


def _set_methods(methods):
    c, cur = _raw()
    cur.execute("UPDATE tenant_settings SET payment_methods = %s", (methods,))
    c.close()


def _product(client, h, name, price, exempt=False):
    return client.post("/api/products/", headers=h, json={
        "name": name, "price": price, "stock": 1000, "is_tax_exempt": exempt}).json()["id"]


def _sell(client, h, pid, qty=1, **extra):
    r = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": qty}], "payment_method": "cash", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _parse(num):
    code, typ, seq = num.split("-")
    return code, typ, int(seq)


def _tlv(b64):
    raw, out, i = base64.b64decode(b64), {}, 0
    while i < len(raw):
        tag, ln = raw[i], raw[i + 1]
        out[tag] = raw[i + 2:i + 2 + ln].decode("utf-8")
        i += 2 + ln
    return out


# ------------------------------------------------------------------ numbering

def test_invoice_numbers_are_per_branch_and_gap_free(client):
    h = login(client)
    pid = _product(client, h, "رقم-تسلسل", 10)
    a, b = _sell(client, h, pid), _sell(client, h, pid)
    ca, ta, na = _parse(a["invoice_number"])
    cb, tb, nb = _parse(b["invoice_number"])
    assert ta == tb == "INV" and ca == cb and nb == na + 1

    # a second branch has its own series starting at 1
    loc = client.post("/api/locations/", headers=h, json={"name": "فرع جدة"}).json()
    assert loc["code"] and loc["code"] != ca
    reg = client.post("/api/registers/", headers=h,
                      json={"name": "صندوق جدة", "location_id": loc["id"]}).json()
    c = _sell(client, h, pid, register_id=reg["id"])
    assert c["invoice_number"] == f"{loc['code']}-INV-000001"
    # …and the first branch continues where it was
    d = _sell(client, h, pid)
    assert _parse(d["invoice_number"]) == (ca, "INV", nb + 1)

    # lookup by number
    got = client.get(f"/api/sales/by-number/{c['invoice_number']}", headers=h)
    assert got.status_code == 200 and got.json()["id"] == c["id"]


def test_concurrent_sales_never_share_a_number(client):
    h = login(client)
    pid = _product(client, h, "تزامن", 5)
    results, errors = [], []

    def worker():
        try:
            with TestClient(main.app) as c2:
                r = c2.post("/api/sales/", headers=h, json={
                    "items": [{"product_id": pid, "quantity": 1}], "payment_method": "cash"})
                (results if r.status_code == 200 else errors).append(r)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    seqs = sorted(_parse(r.json()["invoice_number"])[2] for r in results)
    assert len(set(seqs)) == 8 and seqs == list(range(seqs[0], seqs[0] + 8))


def test_branch_code_locks_after_first_document(client):
    h = login(client)
    loc = client.post("/api/locations/", headers=h, json={"name": "فرع مؤقت", "code": "tmp1"}).json()
    assert loc["code"] == "TMP1" and loc["code_locked"] is False
    ok = client.put(f"/api/locations/{loc['id']}", headers=h, json={"code": "TMP2"})
    assert ok.status_code == 200 and ok.json()["code"] == "TMP2"
    dup = client.put(f"/api/locations/{loc['id']}", headers=h, json={"code": "B01"})
    assert dup.status_code == 400
    reg = client.post("/api/registers/", headers=h, json={"name": "ص", "location_id": loc["id"]}).json()
    _sell(client, h, _product(client, h, "قفل", 3), register_id=reg["id"])
    locked = client.put(f"/api/locations/{loc['id']}", headers=h, json={"code": "TMP3"})
    assert locked.status_code == 400


# ------------------------------------------------------------------ VAT snapshot / QR / hash

def test_vat_snapshot_qr_and_hash_chain(client):
    h = login(client)
    pid = _product(client, h, "خاضع", 115)
    ex = _product(client, h, "معفى", 20, exempt=True)
    r = client.post("/api/sales/", headers=h, json={
        "items": [{"product_id": pid, "quantity": 1}, {"product_id": ex, "quantity": 1}],
        "payment_method": "cash"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["is_tax_invoice"] is True and s["invoice_type"] == "simplified"
    assert (s["total"], s["vat_amount"], s["subtotal"], s["exempt_amount"]) == (135.0, 15.0, 120.0, 20.0)
    lines = {l["product_name"]: l for l in s["items"]}
    assert lines["خاضع"]["vat_rate"] == 15 and lines["خاضع"]["line_vat"] == 15.0
    assert lines["معفى"]["vat_rate"] == 0 and lines["معفى"]["line_vat"] == 0
    assert s["issued_at"].endswith("Z") or s["issued_at"].endswith("+00:00")

    qr = _tlv(s["qr_data"])
    assert qr[2] == s["seller"]["vat_number"] and qr[4] == "135.00" and qr[5] == "15.00"
    assert qr[3].endswith("Z")

    # changing the VAT rate later never changes an issued invoice
    _set_rate(5)
    try:
        again = client.get(f"/api/sales/{s['id']}", headers=h).json()
        assert (again["vat_amount"], again["qr_data"]) == (15.0, s["qr_data"])
    finally:
        _set_rate(15)

    # hash chain: the next invoice in the branch points at this one
    nxt = _sell(client, h, pid)
    c, cur = _raw()
    cur.execute("SELECT invoice_hash FROM sales WHERE id=%s", (s["id"],))
    h1 = cur.fetchone()[0]
    cur.execute("SELECT previous_hash, invoice_hash FROM sales WHERE id=%s", (nxt["id"],))
    prev2, h2 = cur.fetchone()
    c.close()
    assert prev2 == h1 and h2 and h2 != h1


def test_non_vat_registered_tenant_issues_plain_invoice(client):
    h = login(client)
    pid = _product(client, h, "بدون-ضريبة", 50)
    _tenant_flags(vat_enabled=False)
    try:
        s = _sell(client, h, pid)
        assert s["is_tax_invoice"] is False and s["qr_data"] is None
        assert s["vat_amount"] == 0 and s["total"] == 50.0
    finally:
        _tenant_flags(vat_enabled=True)


# ------------------------------------------------------------------ immutability

def test_issued_documents_cannot_be_edited_or_deleted(client):
    h = login(client)
    s = _sell(client, h, _product(client, h, "ثابت", 9))
    c, cur = _raw()
    for stmt in ("UPDATE sales SET total = 1 WHERE id = %s",
                 "DELETE FROM sales WHERE id = %s",
                 "UPDATE sale_items SET price = 1 WHERE sale_id = %s",
                 "DELETE FROM sale_items WHERE sale_id = %s"):
        with pytest.raises(psycopg2.Error):
            cur.execute(stmt, (s["id"],))
    c.close()


# ------------------------------------------------------------------ credit notes

def test_credit_note_requires_reason_and_reverses_original_vat(client):
    h = login(client)
    pid = _product(client, h, "مرتجع-ضريبة", 115)
    s = _sell(client, h, pid, qty=2)
    no_reason = client.post("/api/returns/", headers=h, json={
        "invoice_number": s["invoice_number"], "items": [{"product_id": pid, "quantity": 1}]})
    assert no_reason.status_code == 400

    _set_rate(5)   # a later rate change must not affect the credit note
    try:
        r = client.post("/api/returns/", headers=h, json={
            "invoice_number": s["invoice_number"], "reason": "تالف",
            "items": [{"product_id": pid, "quantity": 1}]})
    finally:
        _set_rate(15)
    assert r.status_code == 200, r.text
    cn = r.json()
    code, typ, _ = _parse(cn["credit_note_number"])
    assert typ == "CN" and code == _parse(s["invoice_number"])[0]
    assert cn["original_invoice_number"] == s["invoice_number"]
    assert (cn["total"], cn["vat_amount"], cn["subtotal"]) == (115.0, 15.0, 100.0)
    assert _tlv(cn["qr_data"])[5] == "15.00"

    by_no = client.get(f"/api/returns/invoice/{s['invoice_number']}", headers=h).json()
    assert by_no["items"][0]["remaining"] == 1


# ------------------------------------------------------------------ donations

def test_donation_rules(client):
    h = login(client)
    cash = client.post("/api/donations/", headers=h, json={"amount": 50, "payment_method": "cash"})
    assert cash.status_code == 400
    no_ref = client.post("/api/donations/", headers=h, json={"amount": 50, "payment_method": "card"})
    assert no_ref.status_code == 400
    r = client.post("/api/donations/", headers=h,
                    json={"amount": 50, "payment_method": "transfer", "donor_name": "فاعل خير"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert _parse(d["receipt_number"])[1] == "DON" and d["status"] == "issued"
    assert "vat_number" not in d["seller"] and "qr_data" not in d
    r2 = client.post("/api/donations/", headers=h,
                     json={"amount": 20, "payment_method": "card", "card_ref": "A1"}).json()
    assert _parse(r2["receipt_number"])[2] == _parse(d["receipt_number"])[2] + 1

    # a donation is never a sale line: the sales endpoint has no donation input
    assert "donation" not in str(client.get("/openapi.json").json()["components"]["schemas"]["SaleCreate"])

    # method must be enabled for the tenant
    _set_methods("cash,card")
    try:
        t = client.post("/api/donations/", headers=h, json={"amount": 5, "payment_method": "transfer"})
        assert t.status_code == 400
    finally:
        _set_methods("cash,card,transfer")


def test_donation_cannot_be_deleted_only_voided(client):
    h = login(client)
    d = client.post("/api/donations/", headers=h,
                    json={"amount": 30, "payment_method": "transfer"}).json()
    assert client.delete(f"/api/donations/{d['id']}", headers=h).status_code == 405
    assert client.post(f"/api/donations/{d['id']}/void", headers=h, json={"reason": " "}).status_code == 400
    v = client.post(f"/api/donations/{d['id']}/void", headers=h, json={"reason": "مكرر"})
    assert v.status_code == 200 and v.json()["status"] == "void"
    assert v.json()["receipt_number"] == d["receipt_number"]
    assert client.post(f"/api/donations/{d['id']}/void", headers=h, json={"reason": "x"}).status_code == 400

    c, cur = _raw()
    for stmt in ("UPDATE donations SET amount = 1 WHERE id = %s",
                 "UPDATE donations SET status = 'issued' WHERE id = %s",
                 "DELETE FROM donations WHERE id = %s"):
        with pytest.raises(psycopg2.Error):
            cur.execute(stmt, (d["id"],))
    # PDPL anonymisation is still allowed
    cur.execute("UPDATE donations SET donor_name = NULL WHERE id = %s", (d["id"],))
    c.close()

    rep = client.get("/api/reports/donations-report", headers=h).json()
    row = next(x for x in rep["donations"] if x["id"] == d["id"])
    assert row["status"] == "void" and rep["summary"]["void_count"] >= 1


def test_donations_flag_off_hides_everything(client):
    h = login(client)
    _tenant_flags(donations_enabled=False)
    try:
        assert client.get("/api/donations/", headers=h).status_code == 403
        assert client.get("/api/reports/donations-report", headers=h).status_code == 403
        dash = client.get("/api/reports/dashboard", headers=h).json()
        assert dash["donations_enabled"] is False
        assert "donations_total" not in dash["today"] and "recent_donations" not in dash
    finally:
        _tenant_flags(donations_enabled=True)
    dash = client.get("/api/reports/dashboard", headers=h).json()
    assert "donations_total" in dash["today"]


def test_sales_report_has_vat_and_credit_notes(client):
    h = login(client)
    rep = client.get("/api/reports/sales-report", headers=h).json()
    s = rep["summary"]
    for k in ("vat_total", "credit_notes_total", "credit_notes_vat", "net_total", "net_vat"):
        assert k in s
    assert round(s["net_total"], 2) == round(s["total"] - s["credit_notes_total"], 2)
    assert all(x["invoice_number"] for x in rep["sales"])
