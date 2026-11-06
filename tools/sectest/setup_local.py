#!/usr/bin/env python3
"""Prepare a LOCAL copy for the security + stress tests.  NEVER run on production.

Run from the backend folder with its venv (it imports the app's own modules):

    cd backend
    .venv/bin/python ../tools/sectest/setup_local.py

Creates (idempotent):
  * tenants  sec-a, sec-b  (non-profit, VAT-registered, complete national address)
    each with users  admin / cashier / locktest  (password below, no forced change)
  * load-test tenants  load-01 … load-NN  (see --load-tenants) with  admin  + cashiers
  * platform admin  sectest  with a KNOWN 2FA secret (so the suite can log in)
Writes  tools/sectest/config.local.json  for security_suite.py and stress_test.py.
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.getcwd())

from config import settings  # noqa: E402

if settings.is_production:
    sys.exit("Refusing to run: ENVIRONMENT is production. This script is for a local copy only.")

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import text  # noqa: E402

import platform_auth as pa  # noqa: E402
from database import (PlatformAdmin, SessionLocal, Tenant, TenantSettings, User,  # noqa: E402
                      ensure_default_branch, ensure_default_uom)

PASSWORD = "SecTest-Pass-2026"
PLATFORM_USER, PLATFORM_PW = "sectest", "SecTest-Platform-2026"
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def pin(db, tid):
    db.execute(text("SELECT set_config('app.current_tenant', :t, false)"), {"t": "" if tid is None else str(tid)})


def ensure_tenant(db, slug, name, users):
    t = db.query(Tenant).filter(Tenant.slug == slug).first()
    if t is None:
        t = Tenant(slug=slug, name=name, entity_type="nonprofit_association", license_number="9001",
                   vat_enabled=True, vat_number="300000000000003", sales_enabled=True,
                   donations_enabled=True, business_type="mixed")
        db.add(t)
        db.commit()
        db.refresh(t)
    pin(db, t.id)
    st = db.query(TenantSettings).filter(TenantSettings.tenant_id == t.id).first()
    if st is None:
        st = TenantSettings(tenant_id=t.id)
        db.add(st)
    st.seller_name, st.vat_number, st.vat_rate = name, "300000000000003", 15
    st.building_number, st.street_name, st.district = "1234", "طريق الاختبار", "حي الاختبار"
    st.city, st.postal_code, st.additional_number = "جدة", "23456", "5678"
    st.short_address, st.country = "JTST1234", "المملكة العربية السعودية"
    st.require_transfer_proof = True
    for username, role in users:
        u = db.query(User).filter(User.username == username).first()
        if u is None:
            u = User(tenant_id=t.id, username=username, full_name=f"{role} {slug}", role=role)
            db.add(u)
        u.password_hash, u.is_active, u.must_change_password = pwd.hash(PASSWORD), True, False
    db.commit()
    ensure_default_branch(db, t.id)
    ensure_default_uom(db, t.id)
    db.execute(text("DELETE FROM login_attempts WHERE tenant_slug=:s"), {"s": slug})
    db.commit()
    pin(db, None)
    return t.id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--platform", default="http://127.0.0.1:8001")
    ap.add_argument("--load-tenants", type=int, default=5)
    ap.add_argument("--cashiers-per-tenant", type=int, default=4)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        ids = {}
        for slug, name in (("sec-a", "جمعية اختبار أ"), ("sec-b", "جمعية اختبار ب")):
            ids[slug] = ensure_tenant(db, slug, name, [("admin", "admin"), ("cashier", "cashier"), ("locktest", "cashier")])
        load = []
        for i in range(1, args.load_tenants + 1):
            slug = f"load-{i:02d}"
            users = [("admin", "admin")] + [(f"cashier{j}", "cashier") for j in range(1, args.cashiers_per_tenant + 1)]
            ensure_tenant(db, slug, f"منشأة تحميل {i}", users)
            load.append({"slug": slug, "admin": "admin",
                         "cashiers": [f"cashier{j}" for j in range(1, args.cashiers_per_tenant + 1)]})

        secret = pa.new_totp_secret()
        a = db.query(PlatformAdmin).filter(PlatformAdmin.username == PLATFORM_USER).first()
        if a is None:
            a = PlatformAdmin(username=PLATFORM_USER, full_name="Security test")
            db.add(a)
        a.password_hash = pwd.hash(PLATFORM_PW)
        a.totp_secret, a.totp_enabled, a.totp_last_step = pa.encrypt_secret(secret), True, None
        a.is_active, a.failed_count, a.locked_until = True, 0, None
        db.commit()
    finally:
        db.close()

    cfg = {
        "mode": "local", "base": args.base, "platform": args.platform, "password": PASSWORD,
        "tenant_a": "sec-a", "tenant_b": "sec-b",
        "users": {"admin": "admin", "cashier": "cashier", "locktest": "locktest"},
        "platform_user": PLATFORM_USER, "platform_password": PLATFORM_PW, "platform_totp_secret": secret,
        "load_tenants": load,
    }
    out = HERE / "config.local.json"
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    print(f"OK  tenants sec-a, sec-b + {len(load)} load tenants ready; platform admin '{PLATFORM_USER}'.")
    print(f"    config written to {out}")


if __name__ == "__main__":
    main()
