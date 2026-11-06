#!/usr/bin/env python3
"""Platform admin CLI for tenants (monitor + manage).

Run from the backend/ folder with the venv active and .env present:

  python manage.py list
  python manage.py create <slug> "<name>" --admin-user admin --admin-pass 'PW'
  python manage.py activate <slug>
  python manage.py deactivate <slug>
  python manage.py delete <slug> --yes      # deletes the tenant AND all its data
  python manage.py identity <slug>          # show the organization identity
  python manage.py identity <slug> --type company --name "..." --name-en "..." \
        --unified 7012345678 --cr 4030123456 --vat 310123456700003 --vat-enabled yes
      types: nonprofit_association nonprofit_foundation endowment cooperative
             company sole_establishment online_store freelancer other
      (identity is platform-controlled: the tenant's admin cannot change it)

  Platform console admins (Release 2b — NOT tenant users):
  python manage.py platform-admin list
  python manage.py platform-admin create <username> "<full name>"   # asks for the password
  python manage.py platform-admin reset-mfa <username>  # re-enrol the authenticator at next login
  python manage.py platform-admin unlock <username>
  python manage.py platform-admin disable|enable <username>
  python manage.py platform-admin set-password <username>           # asks for the password

Counts are RLS-scoped per tenant (the app role sees one tenant at a time), so
this reflects exactly what each organization can see.
"""
import argparse
import sys

from sqlalchemy import text
from passlib.context import CryptContext

from database import SessionLocal, Tenant, TenantSettings, User, Product, Sale, ensure_default_branch, ensure_default_uom

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
    ensure_default_uom(db, t.id)
    print("  default branch 'الفرع الرئيسي' + register 'الصندوق 1' + default units created.")


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
    # Issued invoices / credit notes / donation receipts are immutable (DB trigger);
    # a deliberate whole-tenant purge is the only exception.
    db.execute(text("SELECT set_config('app.allow_purge', 'on', true)"))
    db.delete(t)
    db.commit()
    print(f"Deleted tenant '{args.slug}' and all its data.")


def cmd_identity(db, args):
    import entities
    t = db.query(Tenant).filter(Tenant.slug == args.slug).first()
    if not t:
        print(f"Tenant '{args.slug}' not found.")
        return 1
    _pin(db, t.id)
    st = db.query(TenantSettings).filter(TenantSettings.tenant_id == t.id).first()

    changes = {}
    for arg, field in (("type", "entity_type"), ("name", "name"), ("name_en", "name_en"),
                       ("unified", "unified_number"), ("cr", "cr_number"), ("license", "license_number"),
                       ("freelance", "freelance_doc_number"), ("vat", "vat_number")):
        v = getattr(args, arg)
        if v is not None:
            changes[field] = v.strip() or None
    if args.vat_enabled is not None:
        changes["vat_enabled"] = args.vat_enabled == "yes"
    if args.vat_rate is not None:
        changes["vat_rate"] = args.vat_rate

    if changes:
        errs = entities.validate_identity(changes)
        if errs:
            print("Not saved:\n  - " + "\n  - ".join(errs))
            return 1
        for f, v in changes.items():
            if f == "vat_rate":
                if st is not None:
                    st.vat_rate = v
            else:
                setattr(t, f, v)
        if st is not None and "name" in changes:
            st.seller_name = changes["name"]          # keep the legacy column in step
        if st is not None and "vat_number" in changes:
            st.vat_number = changes["vat_number"]
        if not entities.is_nonprofit(t.entity_type) and t.donations_enabled:
            t.donations_enabled = False
            print("  donations switched OFF (only non-profit organizations can receive donations)")
        db.commit()
        print("Saved.")

    info = entities.info(t.entity_type)
    rows = [
        ("slug", t.slug), ("name (ar)", t.name), ("name (en)", t.name_en),
        ("type", f"{info['entity_type']}  ({info['entity_type_label']} / {info['entity_group']})"),
        ("unified number", t.unified_number), ("CR number", t.cr_number),
        ("licence number", t.license_number), ("freelance doc", t.freelance_doc_number),
        ("VAT number", t.vat_number), ("VAT registered", "yes" if t.vat_enabled else "no"),
        ("VAT rate %", st.vat_rate if st else None),
        ("donations", "on" if (t.donations_enabled and info["entity_group"] == entities.NONPROFIT) else "off"),
    ]
    if info["primary_registration"] and not getattr(t, info["primary_registration"]):
        rows.append(("! missing", info["primary_registration_label"]))
    for k, v in rows:
        print(f"  {k:<16}{'' if v is None else v}")
    return 0


def cmd_platform_admin(db, args):
    import getpass
    from datetime import datetime, timezone
    from database import PlatformAdmin, PlatformAuditLog
    from routers.platform import password_problem

    def log(action, a, detail=None):
        db.add(PlatformAuditLog(admin_id=a.id if a else None, username="cli",
                                action=action, target=a.username if a else None, detail=detail))

    if args.action == "list":
        rows = db.query(PlatformAdmin).order_by(PlatformAdmin.id).all()
        if not rows:
            print("No platform admins yet. Create one: python manage.py platform-admin create <username> \"<name>\"")
        for a in rows:
            print(f"  {a.id:<4}{a.username:<20}{'active' if a.is_active else 'DISABLED':<10}"
                  f"{'2FA on' if a.totp_enabled else '2FA not enrolled':<18}"
                  f"{'LOCKED' if a.locked_until and a.locked_until > datetime.now(timezone.utc) else ''}"
                  f"  last login: {a.last_login_at or '-'}")
        return 0
    if not args.username:
        print("username is required")
        return 1
    a = db.query(PlatformAdmin).filter(PlatformAdmin.username == args.username).first()

    def ask_password():
        pw = args.password or getpass.getpass("Password (min 12, letters + digits): ")
        if not args.password and pw != getpass.getpass("Repeat: "):
            print("Passwords do not match.")
            return None
        err = password_problem(pw)
        if err:
            print("Not saved: " + err)
            return None
        return pw

    if args.action == "create":
        if a:
            print(f"Platform admin '{args.username}' already exists.")
            return 1
        pw = ask_password()
        if not pw:
            return 1
        a = PlatformAdmin(username=args.username, full_name=args.full_name or args.username,
                          password_hash=pwd.hash(pw), password_changed_at=datetime.now(timezone.utc))
        db.add(a)
        db.flush()
        log("admin_created", a)
        db.commit()
        print(f"Created platform admin '{a.username}'. At the first login the console shows a QR "
              f"code: scan it with an authenticator app (Google/Microsoft Authenticator, Authy).")
        return 0
    if not a:
        print(f"Platform admin '{args.username}' not found.")
        return 1
    if args.action == "reset-mfa":
        a.totp_enabled, a.totp_secret, a.totp_last_step = False, None, None
        log("mfa_reset", a)
        msg = "2FA reset: a new QR code will be shown at the next login."
    elif args.action == "unlock":
        a.failed_count, a.locked_until = 0, None
        log("admin_unlocked", a)
        msg = "Unlocked."
    elif args.action in ("disable", "enable"):
        a.is_active = args.action == "enable"
        log(f"admin_{args.action}d", a)
        msg = f"{'Enabled' if a.is_active else 'Disabled'}."
    elif args.action == "set-password":
        pw = ask_password()
        if not pw:
            return 1
        a.password_hash = pwd.hash(pw)
        a.password_changed_at = datetime.now(timezone.utc)
        a.failed_count, a.locked_until = 0, None
        log("admin_password_set", a)
        msg = "Password changed (open sessions are ended)."
    else:
        print("unknown action")
        return 1
    db.commit()
    print(msg)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Bayan POS tenant admin")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List tenants with per-tenant counts")

    c = sub.add_parser("create", help="Create a tenant (and optional admin)")
    c.add_argument("slug")
    c.add_argument("name")
    c.add_argument("--admin-user")
    c.add_argument("--admin-pass")

    i = sub.add_parser("identity", help="Show or set the organization identity (platform-controlled)")
    i.add_argument("slug")
    i.add_argument("--type")
    i.add_argument("--name")
    i.add_argument("--name-en", dest="name_en")
    i.add_argument("--unified")
    i.add_argument("--cr")
    i.add_argument("--license")
    i.add_argument("--freelance")
    i.add_argument("--vat")
    i.add_argument("--vat-enabled", dest="vat_enabled", choices=["yes", "no"])
    i.add_argument("--vat-rate", dest="vat_rate", type=float)

    pa_ = sub.add_parser("platform-admin", help="Manage platform console admins")
    pa_.add_argument("action", choices=["list", "create", "reset-mfa", "unlock", "disable", "enable", "set-password"])
    pa_.add_argument("username", nargs="?")
    pa_.add_argument("full_name", nargs="?")
    pa_.add_argument("--password", help=argparse.SUPPRESS)   # tests / automation only

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
        elif args.command == "identity":
            return cmd_identity(db, args)
        elif args.command == "platform-admin":
            return cmd_platform_admin(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
