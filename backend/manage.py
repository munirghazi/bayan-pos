#!/usr/bin/env python3
"""Platform admin CLI for tenants (monitor + manage).

Run from the backend/ folder with the venv active and .env present:

  python manage.py list
  python manage.py create <slug> "<name>" --admin-user admin --admin-pass 'PW'
  python manage.py activate <slug>
  python manage.py deactivate <slug>
  python manage.py delete <slug> --yes      # deletes the tenant AND all its data

Counts are RLS-scoped per tenant (the app role sees one tenant at a time), so
this reflects exactly what each organization can see.
"""
import argparse
import sys

from sqlalchemy import text
from passlib.context import CryptContext

from database import SessionLocal, Tenant, TenantSettings, User, Product, Sale, ensure_default_branch

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _pin(db, tid: int):
    db.execute(text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(tid)})


def cmd_list(db, args):
    tenants = db.query(Tenant).order_by(Tenant.id).all()
    if not tenants:
        print("No tenants yet.")
        return
    print(f"{'ID':<4}{'SLUG':<16}{'ACTIVE':<8}{'USERS':<7}{'PRODUCTS':<10}{'SALES':<7} NAME")
    print("-" * 72)
    for t in tenants:
        _pin(db, t.id)
        users = db.query(User).count()
        products = db.query(Product).count()
        sales = db.query(Sale).count()
        active = "yes" if t.is_active else "no"
        print(f"{t.id:<4}{t.slug:<16}{active:<8}{users:<7}{products:<10}{sales:<7} {t.name}")
    _pin(db, 0)


def cmd_create(db, args):
    if db.query(Tenant).filter(Tenant.slug == args.slug).first():
        print(f"Tenant '{args.slug}' already exists.")
        return
    t = Tenant(slug=args.slug, name=args.name)
    db.add(t)
    db.commit()
    db.refresh(t)
    _pin(db, t.id)
    db.add(TenantSettings(tenant_id=t.id, seller_name=args.name))
    db.commit()
    if args.admin_user and args.admin_pass:
        db.add(User(tenant_id=t.id, username=args.admin_user,
                    password_hash=pwd.hash(args.admin_pass),
                    full_name="مدير النظام", role="admin", must_change_password=True))
        db.commit()
        print(f"Created tenant '{t.slug}' (id={t.id}) with admin '{args.admin_user}'.")
    else:
        print(f"Created tenant '{t.slug}' (id={t.id}). "
              f"No admin created (pass --admin-user and --admin-pass to add one).")
    ensure_default_branch(db, t.id)
    print("  default branch 'الفرع الرئيسي' + register 'الصندوق 1' created.")


def cmd_set_active(db, args, active: bool):
    t = db.query(Tenant).filter(Tenant.slug == args.slug).first()
    if not t:
        print(f"Tenant '{args.slug}' not found.")
        return
    t.is_active = active
    db.commit()
    print(f"Tenant '{args.slug}' is now {'active' if active else 'inactive'}.")


def cmd_delete(db, args):
    t = db.query(Tenant).filter(Tenant.slug == args.slug).first()
    if not t:
        print(f"Tenant '{args.slug}' not found.")
        return
    if not args.yes:
        print(f"This will PERMANENTLY delete tenant '{t.slug}' (id={t.id}) and ALL its "
              f"data (users, products, sales, ...). Re-run with --yes to confirm.")
        return
    _pin(db, t.id)          # allow RLS-scoped cascade of its rows
    db.delete(t)
    db.commit()
    print(f"Deleted tenant '{args.slug}' and all its data.")


def main():
    parser = argparse.ArgumentParser(description="Bayan POS tenant admin")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List tenants with per-tenant counts")

    c = sub.add_parser("create", help="Create a tenant (and optional admin)")
    c.add_argument("slug")
    c.add_argument("name")
    c.add_argument("--admin-user")
    c.add_argument("--admin-pass")

    for name in ("activate", "deactivate", "delete"):
        p = sub.add_parser(name)
        p.add_argument("slug")
        if name == "delete":
            p.add_argument("--yes", action="store_true", help="confirm permanent deletion")

    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.command == "list":
            cmd_list(db, args)
        elif args.command == "create":
            cmd_create(db, args)
        elif args.command == "activate":
            cmd_set_active(db, args, True)
        elif args.command == "deactivate":
            cmd_set_active(db, args, False)
        elif args.command == "delete":
            cmd_delete(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
