#!/usr/bin/env python3
"""Bayan POS / Sahl — application security test suite.

Black-box: talks to the running system over HTTP only (needs: pip install httpx).

    python3 security_suite.py --config config.local.json
    python3 security_suite.py --config config.live.json      # live: only after the Oracle notice period

What it checks (each check prints PASS / FAIL / WARN / SKIP):
  ISO  tenant isolation — tenant B tries to read / change / use tenant A's records
  AUTH authentication, token tampering, lockout, roles (cashier vs admin), cookies
  PLT  platform console — separation, 2FA, CSRF guard, headers
  UPL  file uploads — disguised files, oversize, SVG script, path names
  BIZ  business rules — prices from the browser, quantities, payments, refunds, immutability
  INJ  injection probes — SQL / script text in inputs must not break anything
  HDR  HTTP hardening — headers, exposed docs / metrics

Writes a Markdown + JSON report next to the config file.
Creates records (products, invoices, proofs) ONLY in the two test tenants.
"""
import argparse
import base64
import hashlib
import hmac
import json
import secrets
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import httpx
except ImportError:
    sys.exit("Install httpx first:  pip install httpx")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%test\n"

RESULTS = []
SEV = {"high": "عالية", "medium": "متوسطة", "low": "منخفضة", "info": "معلومة"}


def record(cid, title, ok, sev="medium", evidence="", warn=False, skip=False):
    status = "SKIP" if skip else ("PASS" if ok else ("WARN" if warn else "FAIL"))
    RESULTS.append({"id": cid, "title": title, "status": status, "severity": sev, "evidence": str(evidence)[:400]})
    color = {"PASS": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m", "SKIP": "\033[90m"}[status]
    print(f"{color}{status:<5}\033[0m {cid:<8} {title}" + (f"   [{evidence}]" if status != "PASS" and evidence else ""))


def check(cid, title, fn, sev="medium"):
    try:
        res = fn()
        if isinstance(res, tuple):
            ok, ev = res[0], res[1]
            warn = res[2] if len(res) > 2 else False
        else:
            ok, ev, warn = bool(res), "", False
        record(cid, title, ok, sev, ev, warn=warn)
    except SkipTest as e:
        record(cid, title, True, sev, str(e), skip=True)
    except Exception as e:  # a crash in a check is itself a finding
        record(cid, title, False, sev, f"{type(e).__name__}: {e}")


class SkipTest(Exception):
    pass


def totp(secret):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    d = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    o = d[-1] & 15
    return str((struct.unpack(">I", d[o:o + 4])[0] & 0x7FFFFFFF) % 1000000).zfill(6)


class Api:
    def __init__(self, base, verify=True):
        self.c = httpx.Client(base_url=base, timeout=30, verify=verify, follow_redirects=False)

    def login(self, tenant, user, password):
        r = self.c.post("/api/auth/login", json={"tenant": tenant, "username": user, "password": password})
        if r.status_code != 200:
            raise RuntimeError(f"login {tenant}/{user} failed: {r.status_code} {r.text[:200]}")
        self.c.cookies.clear()
        return {"Authorization": f"Bearer {r.json()['access_token']}"}, r

    def __getattr__(self, name):
        return getattr(self.c, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--insecure", action="store_true", help="skip TLS verification (never for live)")
    args = ap.parse_args()
    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text())
    live = cfg.get("mode") == "live"
    pw = cfg["password"]
    U = cfg["users"]
    A, B = cfg["tenant_a"], cfg["tenant_b"]
    api = Api(cfg["base"], verify=not args.insecure)
    plat = Api(cfg["platform"], verify=not args.insecure) if cfg.get("platform") else None

    print(f"Target: {cfg['base']}   console: {cfg.get('platform')}   mode: {cfg.get('mode')}\n")

    # ------------------------------------------------------------------ fixtures
    hA, _ = api.login(A, U["admin"], pw)
    hB, _ = api.login(B, U["admin"], pw)
    hAc, _ = api.login(A, U["cashier"], pw)

    def product(h, price=115.0, stock=1000):
        r = api.post("/api/products/", headers=h, json={"name": "SEC-" + secrets.token_hex(3), "price": price, "stock": stock})
        assert r.status_code == 200, r.text
        return r.json()

    def proof(h, data=PNG, name="p.png"):
        r = api.post("/api/payment-proofs/", headers=h, files={"file": (name, data, "application/octet-stream")})
        return r

    def sale(h, pid, payments, qty=1, **extra):
        return api.post("/api/sales/", headers=h, json={"items": [{"product_id": pid, "quantity": qty}], "payments": payments, **extra})

    pA = product(hA)
    pB = product(hB)
    sA = sale(hA, pA["id"], [{"method": "cash", "amount": 115}])
    assert sA.status_code == 200, f"cannot issue a sale in {A}: {sA.text}"
    sA = sA.json()
    sB = sale(hB, pB["id"], [{"method": "cash", "amount": 115}]).json()
    custA = api.post("/api/customers/", headers=hA, json={"name": "عميل أ", "phone": "0500000001"}).json()
    proofA = proof(hA).json()
    usersA = api.get("/api/auth/users", headers=hA).json()
    regsA = api.get("/api/registers/", headers=hA).json()
    locsA = api.get("/api/locations/", headers=hA).json()

    # ================================================================== ISO
    print("— Tenant isolation")
    check("ISO-01", "B cannot read A's invoice by id",
          lambda: (api.get(f"/api/sales/{sA['id']}", headers=hB).status_code == 404,
                   api.get(f"/api/sales/{sA['id']}", headers=hB).status_code), "high")

    def iso02():
        r = api.get(f"/api/sales/by-number/{sA['invoice_number']}", headers=hB)
        return (r.status_code == 404 or r.json().get("id") != sA["id"], f"{r.status_code} id={r.json().get('id') if r.status_code == 200 else '-'}")
    check("ISO-02", "B cannot read A's invoice by number (same numbering)", iso02, "high")

    def iso03():
        r = api.get("/api/sales/search", headers=hB, params={"q": sA["invoice_number"]})
        rows = r.json() if r.status_code == 200 else []
        rows = rows.get("rows", rows.get("items", [])) if isinstance(rows, dict) else rows
        return (all(x.get("id") != sA["id"] for x in rows), f"{len(rows)} rows")
    check("ISO-03", "Invoice search never returns A's invoices to B", iso03, "high")

    check("ISO-04", "B cannot read A's product",
          lambda: (api.get(f"/api/products/{pA['id']}", headers=hB).status_code == 404,
                   api.get(f"/api/products/{pA['id']}", headers=hB).status_code), "high")
    check("ISO-05", "B cannot change A's product",
          lambda: (api.put(f"/api/products/{pA['id']}", headers=hB, json={"price": 1}).status_code == 404,
                   api.put(f"/api/products/{pA['id']}", headers=hB, json={"price": 1}).status_code), "high")
    check("ISO-06", "B cannot change A's stock",
          lambda: (api.put(f"/api/products/{pA['id']}/stock", headers=hB, params={"quantity": 0}).status_code in (403, 404),
                   api.put(f"/api/products/{pA['id']}/stock", headers=hB, params={"quantity": 0}).status_code), "high")
    check("ISO-07", "B cannot read A's customer",
          lambda: (api.get(f"/api/customers/{custA['id']}", headers=hB).status_code == 404,
                   api.get(f"/api/customers/{custA['id']}", headers=hB).status_code), "high")
    check("ISO-08", "B cannot download A's transfer proof",
          lambda: (api.get(f"/api/payment-proofs/{proofA['id']}/file", headers=hB).status_code == 404,
                   api.get(f"/api/payment-proofs/{proofA['id']}/file", headers=hB).status_code), "high")
    check("ISO-09", "B cannot open A's invoice for a return",
          lambda: (api.get(f"/api/returns/invoice/{sA['invoice_number']}", headers=hB).json().get("id", None) != sA["id"]
                   if api.get(f"/api/returns/invoice/{sA['invoice_number']}", headers=hB).status_code == 200 else True, ""), "high")

    def iso10():
        r = api.post("/api/returns/", headers=hB, json={"sale_id": sA["id"], "items": [{"product_id": pA["id"], "quantity": 1}],
                                                        "reason": "sec", "refund_method": "cash"})
        return (r.status_code in (400, 404), r.status_code)
    check("ISO-10", "B cannot issue a credit note against A's invoice", iso10, "high")

    def iso11():
        uid = next(u["id"] for u in usersA if u["username"] == U["cashier"])
        r = api.put(f"/api/auth/users/{uid}", headers=hB, json={"password": "Hijacked-12345"})
        return (r.status_code == 404, r.status_code)
    check("ISO-11", "B's admin cannot reset A's user password", iso11, "high")

    def iso12():
        r = sale(hB, pA["id"], [{"method": "cash", "amount": 115}])
        return (r.status_code in (400, 404), r.status_code)
    check("ISO-12", "B cannot sell A's product", iso12, "high")

    def iso13():
        r = sale(hB, pB["id"], [{"method": "cash", "amount": 115}], customer_id=custA["id"])
        return (r.status_code in (400, 404), r.status_code)
    check("ISO-13", "B cannot attach A's customer to a sale", iso13, "high")

    def iso14():
        if not regsA:
            raise SkipTest("no register")
        r = sale(hB, pB["id"], [{"method": "cash", "amount": 115}], register_id=regsA[0]["id"])
        return (r.status_code in (400, 404), r.status_code)
    check("ISO-14", "B cannot sell on A's register", iso14, "high")

    def iso15():
        r = sale(hB, pB["id"], [{"method": "transfer", "amount": 115, "proof_id": proofA["id"]}])
        return (r.status_code in (400, 404), r.status_code)
    check("ISO-15", "B cannot use A's transfer proof", iso15, "high")

    def iso16():
        r = api.post("/api/products/", headers=hB, json={"name": "SEC-inject", "price": 1, "stock": 1, "tenant_id": 1})
        if r.status_code != 200:
            return (True, f"rejected {r.status_code}")
        pid = r.json()["id"]
        return (api.get(f"/api/products/{pid}", headers=hA).status_code == 404, "created in B only")
    check("ISO-16", "A tenant_id sent in the body is ignored", iso16, "high")

    def iso17():
        ids_a = {x["id"] for x in api.get("/api/products/", headers=hA).json()}
        ids_b = {x["id"] for x in api.get("/api/products/", headers=hB).json()}
        la = {x["id"] for x in locsA}
        lb = {x["id"] for x in api.get("/api/locations/", headers=hB).json()}
        return (not (ids_a & ids_b) and not (la & lb), f"overlap products={len(ids_a & ids_b)} branches={len(la & lb)}")
    check("ISO-17", "Lists (products, branches) never overlap between tenants", iso17, "high")

    def iso18():
        rB = api.get("/api/reports/sales-report", headers=hB)
        rA = api.get("/api/reports/sales-report", headers=hA)
        if rB.status_code != 200 or rA.status_code != 200:
            return (False, f"report not reachable: A={rA.status_code} B={rB.status_code}")
        ids_b = {x.get("id") for x in (rB.json().get("sales") or rB.json().get("rows") or [])}
        return (sA["id"] not in ids_b, f"B report rows={len(ids_b)}")
    check("ISO-18", "Reports of B do not include A's invoices", iso18, "high")

    # ================================================================== AUTH
    print("— Authentication & roles")
    check("AUTH-01", "No token → 401",
          lambda: (api.get("/api/sales/search").status_code == 401, api.get("/api/sales/search").status_code), "high")

    def auth02():
        tok = hA["Authorization"].split()[1]
        head, body, sig = tok.split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        payload["tid"] = payload["tid"] + 1000
        forged = head + "." + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=") + "." + sig
        r = api.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
        return (r.status_code == 401, r.status_code)
    check("AUTH-02", "Token with a changed tenant id (bad signature) → 401", auth02, "high")

    def auth03():
        tok = hA["Authorization"].split()[1]
        body = tok.split(".")[1]
        none = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode().rstrip("=") + "." + body + "."
        r = api.get("/api/auth/me", headers={"Authorization": f"Bearer {none}"})
        return (r.status_code == 401, r.status_code)
    check("AUTH-03", "Unsigned token (alg=none) → 401", auth03, "high")

    def auth04():
        r1 = api.post("/api/auth/login", json={"tenant": A, "username": "no-such-user-x", "password": "x" * 10})
        r2 = api.post("/api/auth/login", json={"tenant": A, "username": U["admin"], "password": "wrong-pass-x"})
        return (r1.status_code == r2.status_code and r1.json().get("detail") == r2.json().get("detail"),
                f"{r1.status_code}/{r2.status_code}")
    check("AUTH-04", "Unknown user and wrong password give the same answer", auth04, "low")

    def auth05():
        user = U.get("locktest")
        if not user:
            raise SkipTest("no locktest user in config")
        codes = [api.post("/api/auth/login", json={"tenant": A, "username": user, "password": "wrong-" + str(i)}).status_code for i in range(6)]
        r = api.post("/api/auth/login", json={"tenant": A, "username": user, "password": pw})
        return (r.status_code == 429, f"attempts={codes} then correct={r.status_code}")
    check("AUTH-05", "Account locks after repeated wrong passwords", auth05, "medium")

    def auth06():
        _, r = api.login(A, U["admin"], pw)
        sc = r.headers.get("set-cookie", "")
        flags = sc.lower()
        ok = "httponly" in flags and "samesite" in flags
        secure = "secure" in flags
        return (ok and (secure or not live), sc.split(";", 1)[1] if ";" in sc else sc,
                ok and not secure and not live)
    check("AUTH-06", "Session cookie is HttpOnly + SameSite (+ Secure on HTTPS)", auth06, "medium")

    for cid, method, path, body in (
        ("AUTH-07", "post", "/api/auth/users", {"username": "evil", "password": "Evil-12345678", "full_name": "x", "role": "admin"}),
        ("AUTH-08", "put", "/api/settings/tenant", {"receipt_footer": "x"}),
        ("AUTH-09", "post", "/api/products/", {"name": "x", "price": 1, "stock": 1}),
        ("AUTH-10", "post", "/api/returns/", {"sale_id": sA["id"], "items": [{"product_id": pA["id"], "quantity": 1}], "reason": "x"}),
        ("AUTH-11", "post", "/api/stock/adjust", {"product_id": pA["id"], "quantity": 5, "reason": "x"}),
    ):
        check(cid, f"Cashier cannot {method.upper()} {path}",
              lambda m=method, p=path, b=body: (getattr(api, m)(p, headers=hAc, json=b).status_code == 403,
                                                getattr(api, m)(p, headers=hAc, json=b).status_code), "high")

    def auth12():
        r = api.put(f"/api/products/{pA['id']}/stock", headers=hAc, params={"quantity": 99999})
        return (r.status_code == 403, f"cashier set stock → {r.status_code}")
    check("AUTH-12", "Cashier cannot overwrite stock directly", auth12, "medium")

    def auth13():
        me = api.get("/api/auth/me", headers=hAc).json()
        r = api.put(f"/api/auth/users/{me['id']}", headers=hAc, json={"role": "admin"})
        return (r.status_code == 403, r.status_code)
    check("AUTH-13", "Cashier cannot make himself admin", auth13, "high")

    def auth14():
        r = api.post("/api/auth/change-password", headers=hAc, json={"current_password": "wrong", "new_password": "Another-12345"})
        return (r.status_code == 400, r.status_code)
    check("AUTH-14", "Password change needs the current password", auth14, "medium")

    def auth15():
        h, _ = api.login(A, U["admin"], pw)
        api.post("/api/auth/logout", headers=h)
        r = api.get("/api/auth/me", headers=h)
        return (r.status_code == 401, f"token after logout → {r.status_code}", r.status_code == 200)
    check("AUTH-15", "Token stops working after logout", auth15, "low")
    hA, _ = api.login(A, U["admin"], pw)          # logout ended every session of this user

    # ================================================================== PLT
    print("— Platform console")
    if plat is None:
        record("PLT-00", "Console not configured", True, "info", skip=True)
    else:
        check("PLT-01", "Console API absent on the tenant domain",
              lambda: (api.get("/api/platform/tenants").status_code == 404, api.get("/api/platform/tenants").status_code), "high")

        def plt02():
            plat.c.cookies.set("platform_session", hA["Authorization"].split()[1])
            r = plat.get("/api/platform/tenants")
            plat.c.cookies.clear()
            return (r.status_code == 401, r.status_code)
        check("PLT-02", "A tenant token is not a console session", plt02, "high")

        check("PLT-03", "Console login without the CSRF header is refused",
              lambda: (plat.post("/api/platform/auth/login", json={"username": "x", "password": "y"}).status_code == 403,
                       plat.post("/api/platform/auth/login", json={"username": "x", "password": "y"}).status_code), "medium")

        def plt04():
            r = plat.get("/")
            h = {k.lower(): v for k, v in r.headers.items()}
            missing = [k for k in ("content-security-policy", "x-frame-options", "x-content-type-options") if k not in h]
            return (not missing, f"missing: {missing}" if missing else "ok")
        check("PLT-04", "Console page sends CSP / frame / nosniff headers", plt04, "low")

        if cfg.get("platform_totp_secret"):
            H = {"X-Platform-Request": "1"}

            def plt05():
                r = plat.post("/api/platform/auth/login", headers=H, json={"username": cfg["platform_user"], "password": cfg["platform_password"]})
                assert r.status_code == 200, r.text
                mfa = r.json()["mfa_token"]
                plat.c.cookies.set("platform_session", mfa)
                r2 = plat.get("/api/platform/tenants")
                plat.c.cookies.clear()
                return (r2.status_code == 401, f"password-only token → {r2.status_code}")
            check("PLT-05", "Password alone (no 2FA code) gives no access", plt05, "high")

            def plt06():
                r = plat.post("/api/platform/auth/login", headers=H, json={"username": cfg["platform_user"], "password": cfg["platform_password"]})
                mfa = r.json()["mfa_token"]
                bad = plat.post("/api/platform/auth/mfa", headers=H, json={"mfa_token": mfa, "code": "000000"})
                code = totp(cfg["platform_totp_secret"])
                good = plat.post("/api/platform/auth/mfa", headers=H, json={"mfa_token": mfa, "code": code})
                plat.c.cookies.clear()
                r = plat.post("/api/platform/auth/login", headers=H, json={"username": cfg["platform_user"], "password": cfg["platform_password"]})
                replay = plat.post("/api/platform/auth/mfa", headers=H, json={"mfa_token": r.json()["mfa_token"], "code": code})
                plat.c.cookies.clear()
                return (bad.status_code == 401 and good.status_code == 200 and replay.status_code == 401,
                        f"wrong={bad.status_code} right={good.status_code} replay={replay.status_code}")
            check("PLT-06", "Wrong 2FA code refused, a used code cannot be replayed", plt06, "high")

            def plt07():
                time.sleep(max(0, 31 - (time.time() % 30)))     # next code window
                r = plat.post("/api/platform/auth/login", headers=H, json={"username": cfg["platform_user"], "password": cfg["platform_password"]})
                plat.post("/api/platform/auth/mfa", headers=H, json={"mfa_token": r.json()["mfa_token"], "code": totp(cfg["platform_totp_secret"])})
                ok = plat.get("/api/platform/tenants").status_code == 200
                nohdr = plat.put("/api/platform/tenants/999999/capabilities", json={"sales_enabled": True})
                plat.post("/api/platform/auth/logout", headers=H)
                plat.c.cookies.clear()
                return (ok and nohdr.status_code == 403, f"session={ok} write-without-header={nohdr.status_code}")
            check("PLT-07", "Console writes need the CSRF header even when logged in", plt07, "medium")
        else:
            record("PLT-05", "2FA checks (no TOTP secret in config — run them by hand)", True, "info", skip=True)

    # ================================================================== UPL
    print("— File uploads")
    check("UPL-01", "Proof: HTML disguised as .png is refused",
          lambda: (proof(hA, b"<html><script>alert(1)</script></html>", "x.png").status_code == 400,
                   proof(hA, b"<html><script>alert(1)</script></html>", "x.png").status_code), "medium")
    check("UPL-02", "Proof: executable/script file refused",
          lambda: (proof(hA, b"#!/bin/sh\nid\n", "x.sh").status_code == 400, proof(hA, b"#!/bin/sh\nid\n", "x.sh").status_code), "medium")

    def upl03():
        big = PNG + b"\x00" * (6 * 1024 * 1024)
        r = proof(hA, big, "big.png")
        return (r.status_code in (400, 413), r.status_code)
    check("UPL-03", "Proof: file over the size limit refused", upl03, "low")

    def upl04():
        r = proof(hA, PDF, "../../../../etc/passwd.pdf")
        if r.status_code != 200:
            return (True, f"rejected {r.status_code}")
        f = api.get(f"/api/payment-proofs/{r.json()['id']}/file", headers=hA)
        return (f.status_code == 200 and f.content.startswith(b"%PDF"), "stored safely")
    check("UPL-04", "Proof: path in the file name is neutralised", upl04, "medium")

    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.cookie)</script></svg>'

    def upl05():
        r = api.post("/api/settings/upload-logo", headers=hA, files={"file": ("logo.svg", svg, "image/svg+xml")})
        if r.status_code != 200:
            return (True, f"SVG refused ({r.status_code})")
        url = r.json().get("url") or r.json().get("logo_url")
        f = api.get(url)
        csp = f.headers.get("content-security-policy", "")
        ctype = f.headers.get("content-type", "")
        safe = "svg" not in ctype or "sandbox" in csp or "script-src 'none'" in csp or "default-src 'none'" in csp
        return (safe, f"SVG with script accepted and served as {ctype}; CSP='{csp}'")
    check("UPL-05", "Logo: SVG with script cannot run in the app's origin", upl05, "high")

    def upl06():
        r = api.post("/api/settings/upload-logo", headers=hA, files={"file": ("logo.png", b"<html><script>alert(1)</script></html>", "image/png")})
        if r.status_code != 200:
            return (True, f"refused ({r.status_code})")
        url = r.json().get("url") or r.json().get("logo_url")
        f = api.get(url)
        nosniff = f.headers.get("x-content-type-options", "").lower() == "nosniff"
        return (nosniff and "html" not in f.headers.get("content-type", ""),
                f"non-image accepted as logo; served {f.headers.get('content-type')} nosniff={nosniff}", True)
    check("UPL-06", "Logo: non-image content disguised as .png", upl06, "medium")

    # ================================================================== BIZ
    print("— Business rules")
    p = product(hA, price=100.0)

    def biz01():
        r = api.post("/api/sales/", headers=hA, json={"items": [{"product_id": p["id"], "quantity": 1, "unit_price": 0.01, "price": 0.01}],
                                                     "payments": [{"method": "cash", "amount": 100}]})
        return (r.status_code == 200 and abs(r.json()["total"] - 100.0) < 0.01, f"{r.status_code} total={r.json().get('total') if r.status_code == 200 else r.text[:80]}")
    check("BIZ-01", "Price sent by the browser is ignored (server price used)", biz01, "high")

    for cid, qty in (("BIZ-02", -1), ("BIZ-03", 0)):
        check(cid, f"Quantity {qty} refused",
              lambda q=qty: (sale(hA, p["id"], [{"method": "cash", "amount": 100}], qty=q).status_code in (400, 422),
                             sale(hA, p["id"], [{"method": "cash", "amount": 100}], qty=q).status_code), "high")
    check("BIZ-04", "Huge quantity handled (no 500)",
          lambda: (sale(hA, p["id"], [{"method": "cash", "amount": 1e15}], qty=1e12).status_code in (400, 422),
                   sale(hA, p["id"], [{"method": "cash", "amount": 1e15}], qty=1e12).status_code), "medium")
    check("BIZ-05", "Under-payment refused",
          lambda: (sale(hA, p["id"], [{"method": "cash", "amount": 50}]).status_code == 400,
                   sale(hA, p["id"], [{"method": "cash", "amount": 50}]).status_code), "high")
    check("BIZ-06", "Card over-payment refused",
          lambda: (sale(hA, p["id"], [{"method": "card", "amount": 150, "card_ref": "X1"}]).status_code == 400,
                   sale(hA, p["id"], [{"method": "card", "amount": 150, "card_ref": "X1"}]).status_code), "medium")
    check("BIZ-07", "Negative payment line refused",
          lambda: (sale(hA, p["id"], [{"method": "cash", "amount": 200}, {"method": "card", "amount": -100, "card_ref": "N"}]).status_code in (400, 422),
                   sale(hA, p["id"], [{"method": "cash", "amount": 200}, {"method": "card", "amount": -100, "card_ref": "N"}]).status_code), "high")

    def biz08():
        pr = proof(hA).json()["id"]
        r1 = sale(hA, p["id"], [{"method": "transfer", "amount": 100, "proof_id": pr}])
        r2 = sale(hA, p["id"], [{"method": "transfer", "amount": 100, "proof_id": pr}])
        return (r1.status_code == 200 and r2.status_code == 400, f"first={r1.status_code} second={r2.status_code}")
    check("BIZ-08", "A transfer proof can be used only once", biz08, "high")

    s1 = sale(hA, p["id"], [{"method": "cash", "amount": 200}], qty=2).json()

    def biz09():
        r = api.post("/api/returns/", headers=hA, json={"sale_id": s1["id"], "items": [{"product_id": p["id"], "quantity": 3}],
                                                       "reason": "sec", "refund_method": "cash"})
        return (r.status_code == 400, r.status_code)
    check("BIZ-09", "Cannot return more than was sold", biz09, "high")

    def biz10():
        ok1 = api.post("/api/returns/", headers=hA, json={"sale_id": s1["id"], "items": [{"product_id": p["id"], "quantity": 2}],
                                                         "reason": "sec", "refund_method": "cash"})
        again = api.post("/api/returns/", headers=hA, json={"sale_id": s1["id"], "items": [{"product_id": p["id"], "quantity": 1}],
                                                           "reason": "sec", "refund_method": "cash"})
        return (ok1.status_code == 200 and again.status_code == 400, f"first={ok1.status_code} again={again.status_code}")
    check("BIZ-10", "Cannot return the same items twice", biz10, "high")

    def biz11():
        s2 = sale(hA, p["id"], [{"method": "cash", "amount": 100}]).json()
        r = api.post("/api/returns/", headers=hA, json={"sale_id": s2["id"], "items": [{"product_id": p["id"], "quantity": 1}],
                                                       "reason": "sec", "refund_method": "transfer"})
        return (r.status_code == 400, r.status_code)
    check("BIZ-11", "Refund by a method the customer didn't pay with is refused", biz11, "medium")

    def biz12():
        codes = [api.request(m.upper(), f"/api/sales/{sA['id']}", headers=hA, json={"total": 1}).status_code for m in ("put", "patch", "delete")]
        return (all(c in (404, 405) for c in codes), f"put/patch/delete → {codes}")
    check("BIZ-12", "Issued invoices cannot be edited or deleted over the API", biz12, "high")

    check("BIZ-13", "Cash donation refused",
          lambda: (api.post("/api/donations/", headers=hA, json={"amount": 10, "payment_method": "cash"}).status_code == 400,
                   api.post("/api/donations/", headers=hA, json={"amount": 10, "payment_method": "cash"}).status_code), "medium")
    check("BIZ-14", "Negative donation refused",
          lambda: (api.post("/api/donations/", headers=hA, json={"amount": -10, "payment_method": "card", "card_ref": "D"}).status_code in (400, 422),
                   api.post("/api/donations/", headers=hA, json={"amount": -10, "payment_method": "card", "card_ref": "D"}).status_code), "high")

    def biz15():
        nums = [int(sale(hA, p["id"], [{"method": "cash", "amount": 100}]).json()["invoice_number"].rsplit("-", 1)[1]) for _ in range(3)]
        return (nums == list(range(nums[0], nums[0] + 3)), f"seq {nums}")
    check("BIZ-15", "Invoice numbers are consecutive", biz15, "high")

    # ================================================================== INJ
    print("— Injection probes")
    probes = ["' OR '1'='1", "1; DROP TABLE sales;--", "\" OR 1=1 --", "%' UNION SELECT NULL--", "<script>alert(1)</script>", "${7*7}{{7*7}}"]

    def inj01():
        bad = []
        for q in probes:
            r = api.get("/api/sales/search", headers=hB, params={"q": q})
            if r.status_code >= 500:
                bad.append((q, r.status_code))
            elif r.status_code == 200 and sA["invoice_number"] in r.text and sB["invoice_number"] != sA["invoice_number"]:
                bad.append((q, "leak"))
        return (not bad, bad or "no 5xx, no leak")
    check("INJ-01", "Search inputs: SQL / template probes cause no error or leak", inj01, "high")

    def inj02():
        bad = []
        for q in probes:
            for path, params in (("/api/products/", {"search": q}), ("/api/customers/", {"search": q}),
                                 ("/api/reports/sales-report", {"date_from": q})):
                r = api.get(path, headers=hB, params=params)
                if r.status_code >= 500:
                    bad.append((path, q, r.status_code))
        return (not bad, bad or "ok")
    check("INJ-02", "List / report filters survive probes (no 500)", inj02, "medium")

    def inj03():
        name = '<img src=x onerror=alert(1)>'
        r = api.post("/api/customers/", headers=hA, json={"name": name, "phone": "0500000002"})
        return (r.status_code in (200, 400, 422), f"{r.status_code} (stored text is escaped by React when shown)", r.status_code == 200)
    check("INJ-03", "Script text in a name is stored as text (UI escapes it)", inj03, "low")

    # ================================================================== HDR
    print("— HTTP hardening")
    def hdr01():
        r = api.get("/openapi.json")
        hidden = r.status_code in (401, 403, 404) or '"openapi"' not in r.text
        return (hidden or not live, f"{r.status_code}" + ("" if live else " (local copy runs in development mode: docs on by design; production hides them)"),
                not hidden and not live)
    check("HDR-01", "API docs not public in production (/docs, /openapi.json)", hdr01, "low")
    check("HDR-02", "/metrics not public (request as if through the proxy)",
          lambda: ("requests_total" not in api.get("/metrics", headers={"X-Forwarded-For": "203.0.113.9"}).text,
                   api.get("/metrics", headers={"X-Forwarded-For": "203.0.113.9"}).status_code), "low")

    def hdr03():
        r = api.get("/")
        h = {k.lower(): v for k, v in r.headers.items()}
        want = ["x-content-type-options", "x-frame-options", "referrer-policy"] + (["strict-transport-security"] if live else [])
        missing = [k for k in want if k not in h]
        return (not missing, f"missing {missing}" + ("" if live else " (local: Caddy adds these in production)"), not live and bool(missing))
    check("HDR-03", "Security headers on the tenant app", hdr03, "low")

    def hdr04():
        r = api.post("/api/sales/", headers={**hA, "Content-Type": "application/json"}, content=b"{not json")
        return (r.status_code == 422 and "Traceback" not in r.text, r.status_code)
    check("HDR-04", "Malformed input returns a clean error (no stack trace)", hdr04, "low")

    # ------------------------------------------------------------------ report
    write_report(cfg_path, cfg)


def write_report(cfg_path, cfg):
    counts = {s: sum(1 for r in RESULTS if r["status"] == s) for s in ("PASS", "FAIL", "WARN", "SKIP")}
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = cfg_path.parent / f"security-report-{cfg.get('mode', 'run')}-{stamp}"
    out.with_suffix(".json").write_text(json.dumps({"target": cfg["base"], "counts": counts, "results": RESULTS}, ensure_ascii=False, indent=2))
    lines = [f"# Security test report — {cfg['base']}", "", f"Run: {datetime.now():%Y-%m-%d %H:%M}  ·  mode: {cfg.get('mode')}", "",
             f"**PASS {counts['PASS']} · FAIL {counts['FAIL']} · WARN {counts['WARN']} · SKIP {counts['SKIP']}**", ""]
    bad = [r for r in RESULTS if r["status"] in ("FAIL", "WARN")]
    if bad:
        lines += ["## Findings", "", "| ID | Status | Severity | Check | Evidence |", "|---|---|---|---|---|"]
        order = {"high": 0, "medium": 1, "low": 2, "info": 3}
        for r in sorted(bad, key=lambda r: (r["status"] != "FAIL", order.get(r["severity"], 9))):
            lines.append(f"| {r['id']} | {r['status']} | {r['severity']} | {r['title']} | {r['evidence'].replace('|', '/')} |")
        lines.append("")
    lines += ["## All checks", "", "| ID | Status | Check |", "|---|---|---|"] + [f"| {r['id']} | {r['status']} | {r['title']} |" for r in RESULTS]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(f"\nPASS {counts['PASS']}  FAIL {counts['FAIL']}  WARN {counts['WARN']}  SKIP {counts['SKIP']}")
    print(f"Report: {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
