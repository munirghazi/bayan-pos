"""Release 2b — platform console API (mounted ONLY by platform_main.py).

Auth:     /api/platform/auth/{login, mfa, logout, me, change-password}
Tenants:  /api/platform/tenants …
Audit:    /api/platform/audit

RLS stays on: tenant rows are read by pinning `app.current_tenant` to one
tenant at a time (`_pin`), exactly like manage.py. The `tenants` table itself
has no tenant_id and is visible to the app role.
"""
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

import entities
import platform_auth as pa
from config import settings
from database import (Location, PlatformAdmin, PlatformAuditLog, Register, Tenant,
                      TenantSettings, User, ensure_default_branch, ensure_default_uom)

router = APIRouter()
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,50}$")
VERIFICATION = ("verified", "pending", "limited", "rejected")
GENERIC_LOGIN_ERROR = "اسم المستخدم أو كلمة المرور غير صحيحة"


def _now():
    return datetime.now(timezone.utc)


def _pin(db: Session, tid: int | None):
    db.execute(text("SELECT set_config('app.current_tenant', :t, false)"),
               {"t": "" if tid is None else str(int(tid))})


# =================================================================== auth

class LoginIn(BaseModel):
    username: str
    password: str


class MfaIn(BaseModel):
    mfa_token: str
    code: str


class ChangePwIn(BaseModel):
    current_password: str
    new_password: str
    code: str               # fresh TOTP code: a stolen session alone can't change the password


def _admin_out(a: PlatformAdmin) -> dict:
    return {"id": a.id, "username": a.username, "full_name": a.full_name, "email": a.email,
            "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
            "last_login_ip": a.last_login_ip}


def _fail(db: Session, request: Request, admin: PlatformAdmin | None, username: str, stage: str):
    if admin is not None:
        admin.failed_count = (admin.failed_count or 0) + 1
        if admin.failed_count >= settings.platform_max_login_attempts:
            admin.locked_until = _now() + timedelta(minutes=settings.platform_lockout_minutes)
            admin.failed_count = 0
            pa.audit(db, request, "login_locked", admin=admin)
    pa.audit(db, request, "login_failed", admin=admin, username=username[:50], detail={"stage": stage})
    db.commit()


def _locked(admin: PlatformAdmin) -> bool:
    return bool(admin.locked_until and admin.locked_until > _now())


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(pa.get_platform_db)):
    if request.headers.get("X-Platform-Request") != "1":
        raise HTTPException(status_code=403, detail="طلب غير مسموح")
    admin = db.query(PlatformAdmin).filter(PlatformAdmin.username == body.username.strip()).first()
    if admin is not None and _locked(admin):
        raise HTTPException(status_code=429, detail="تم قفل الحساب مؤقتاً بسبب محاولات متكررة. حاول لاحقاً.")
    if admin is None or not admin.is_active or not pwd.verify(body.password, admin.password_hash):
        if admin is None:
            pwd.hash(body.password)          # same timing whether or not the user exists
        _fail(db, request, admin, body.username, "password")
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    out = {"mfa_token": pa.make_mfa_token(admin.id), "enroll": not admin.totp_enabled}
    if not admin.totp_enabled:
        # First login: (re)issue a secret to scan. It only becomes active once a
        # valid code from it is entered at /auth/mfa.
        secret = pa.new_totp_secret()
        admin.totp_secret = pa.encrypt_secret(secret)
        admin.totp_last_step = None
        db.commit()
        out.update(secret=secret, otpauth_uri=pa.otpauth_uri(secret, admin.username),
                   issuer=settings.platform_issuer)
    return out


@router.post("/auth/mfa")
def mfa(body: MfaIn, request: Request, response: Response, db: Session = Depends(pa.get_platform_db)):
    if request.headers.get("X-Platform-Request") != "1":
        raise HTTPException(status_code=403, detail="طلب غير مسموح")
    payload = pa.decode(body.mfa_token, pa.SCOPE_MFA)
    if not payload:
        raise HTTPException(status_code=401, detail="انتهت مهلة الدخول، أعد إدخال كلمة المرور")
    admin = db.get(PlatformAdmin, int(payload["aid"]))
    if admin is None or not admin.is_active:
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    if _locked(admin):
        raise HTTPException(status_code=429, detail="تم قفل الحساب مؤقتاً بسبب محاولات متكررة. حاول لاحقاً.")
    secret = pa.decrypt_secret(admin.totp_secret)
    step = pa.verify_totp(secret, body.code, admin.totp_last_step) if secret else None
    if step is None:
        _fail(db, request, admin, admin.username, "totp")
        raise HTTPException(status_code=401, detail="رمز التحقق غير صحيح")

    enrolled_now = not admin.totp_enabled
    admin.totp_enabled = True
    admin.totp_last_step = step
    admin.failed_count = 0
    admin.locked_until = None
    admin.last_login_at = _now()
    admin.last_login_ip = pa.client_ip(request)
    if enrolled_now:
        pa.audit(db, request, "mfa_enrolled", admin=admin)
    pa.audit(db, request, "login", admin=admin)
    db.commit()
    pa.set_session_cookie(response, pa.make_session_token(admin.id))
    return {"admin": _admin_out(admin)}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(pa.get_platform_db)):
    token = request.cookies.get(settings.platform_cookie_name)
    p = pa.decode(token, pa.SCOPE_SESSION) if token else None
    if p:
        admin = db.get(PlatformAdmin, int(p["aid"]))
        if admin:
            pa.audit(db, request, "logout", admin=admin)
            db.commit()
    pa.clear_session_cookie(response)
    return {"ok": True}


@router.get("/auth/me")
def me(admin: PlatformAdmin = Depends(pa.require_platform_admin)):
    return {"admin": _admin_out(admin), "session_minutes": settings.platform_session_minutes}


@router.post("/auth/change-password")
def change_password(body: ChangePwIn, request: Request, response: Response,
                    admin: PlatformAdmin = Depends(pa.require_platform_admin),
                    db: Session = Depends(pa.get_platform_db)):
    if not pwd.verify(body.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")
    step = pa.verify_totp(pa.decrypt_secret(admin.totp_secret) or "", body.code, admin.totp_last_step)
    if step is None:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح")
    err = password_problem(body.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    admin.password_hash = pwd.hash(body.new_password)
    admin.password_changed_at = _now()
    admin.totp_last_step = step
    pa.audit(db, request, "password_changed", admin=admin)
    db.commit()
    pa.clear_session_cookie(response)        # log in again with the new password
    return {"ok": True}


def password_problem(pw: str) -> str | None:
    if len(pw or "") < 12:
        return "كلمة المرور يجب ألا تقل عن 12 حرفاً"
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        return "كلمة المرور يجب أن تحتوي على حروف وأرقام"
    return None


# =================================================================== tenants: helpers

def _get_tenant(db: Session, tid: int) -> Tenant:
    t = db.get(Tenant, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="المنشأة غير موجودة")
    return t


def _stats(db: Session, tid: int) -> dict:
    _pin(db, tid)
    row = db.execute(text("""
        SELECT (SELECT count(*) FROM users)                 AS users,
               (SELECT count(*) FROM locations)             AS branches,
               (SELECT count(*) FROM registers)             AS registers,
               (SELECT count(*) FROM products)              AS products,
               (SELECT count(*) FROM sales)                 AS sales,
               (SELECT count(*) FROM returns)               AS credit_notes,
               (SELECT count(*) FROM donations)             AS donations,
               (SELECT max(issued_at) FROM sales)           AS last_sale_at,
               (SELECT max(issued_at) FROM donations)       AS last_donation_at
    """)).mappings().first()
    _pin(db, None)
    d = dict(row)
    d["documents"] = d["sales"] + d["credit_notes"] + d["donations"]
    last = [x for x in (d.pop("last_sale_at"), d.pop("last_donation_at")) if x]
    d["last_activity_at"] = max(last).isoformat() if last else None
    return d


def _business_type(sales: bool, donations: bool) -> str:
    if sales and donations:
        return "mixed"
    return "donation" if donations else "trade"


def _tenant_out(t: Tenant, st: TenantSettings | None = None) -> dict:
    ent = entities.info(t.entity_type)
    donations_effective = bool(t.donations_enabled) and ent["entity_group"] == entities.NONPROFIT
    missing = []
    if ent["primary_registration"] and not getattr(t, ent["primary_registration"]):
        missing.append(ent["primary_registration_label"])
    if t.vat_enabled and not t.vat_number:
        missing.append("الرقم الضريبي")
    return {
        "id": t.id, "slug": t.slug, "name": t.name, "name_en": t.name_en,
        "entity_type": ent["entity_type"], "entity_type_label": ent["entity_type_label"],
        "entity_group": ent["entity_group"], "primary_registration": ent["primary_registration"],
        "unified_number": t.unified_number, "cr_number": t.cr_number,
        "license_number": t.license_number, "freelance_doc_number": t.freelance_doc_number,
        "vat_enabled": bool(t.vat_enabled), "vat_number": t.vat_number,
        "vat_rate": st.vat_rate if st else None,
        "business_type": t.business_type,
        "sales_enabled": bool(t.sales_enabled), "donations_enabled": bool(t.donations_enabled),
        "donations_effective": donations_effective,
        "purchasing_enabled": bool(t.purchasing_enabled), "inventory_enabled": bool(t.inventory_enabled),
        "show_powered_by": bool(t.show_powered_by), "verification_status": t.verification_status,
        "is_active": bool(t.is_active),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "missing": missing,
    }


def _settings(db: Session, tid: int) -> TenantSettings | None:
    _pin(db, tid)
    st = db.query(TenantSettings).filter(TenantSettings.tenant_id == tid).first()
    return st


class IdentityIn(BaseModel):
    name: str | None = None
    name_en: str | None = None
    entity_type: str | None = None
    unified_number: str | None = None
    cr_number: str | None = None
    license_number: str | None = None
    freelance_doc_number: str | None = None
    vat_enabled: bool | None = None
    vat_number: str | None = None
    vat_rate: float | None = None


class CapsIn(BaseModel):
    sales_enabled: bool | None = None
    donations_enabled: bool | None = None
    purchasing_enabled: bool | None = None
    inventory_enabled: bool | None = None
    show_powered_by: bool | None = None
    verification_status: str | None = None


_ID_FIELDS = ("name", "name_en", "entity_type", "unified_number", "cr_number", "license_number",
              "freelance_doc_number", "vat_enabled", "vat_number")


def _clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _apply_identity(db: Session, t: Tenant, st: TenantSettings | None, body: IdentityIn) -> dict:
    data = {k: _clean(v) for k, v in body.model_dump(exclude_unset=True).items()}
    if "name" in data and not data["name"]:
        raise HTTPException(status_code=400, detail="الاسم القانوني (عربي) مطلوب")
    if "entity_type" in data and not data["entity_type"]:
        raise HTTPException(status_code=400, detail="نوع المنشأة مطلوب")
    errs = entities.validate_identity(data)
    vat_on = data.get("vat_enabled", t.vat_enabled)
    vat_no = data["vat_number"] if "vat_number" in data else t.vat_number
    if vat_on and not vat_no:
        errs.append("الرقم الضريبي مطلوب للمنشأة المسجلة في ضريبة القيمة المضافة")
    if errs:
        raise HTTPException(status_code=400, detail="، ".join(errs))

    changes = {}
    for f in _ID_FIELDS:
        if f in data and getattr(t, f) != data[f]:
            changes[f] = {"from": getattr(t, f), "to": data[f]}
            setattr(t, f, data[f])
    if "vat_rate" in data and data["vat_rate"] is not None and st is not None and st.vat_rate != data["vat_rate"]:
        changes["vat_rate"] = {"from": st.vat_rate, "to": data["vat_rate"]}
        st.vat_rate = data["vat_rate"]
    if st is not None:
        st.seller_name = t.name                  # legacy columns kept in step
        st.vat_number = t.vat_number
    if not entities.is_nonprofit(t.entity_type) and t.donations_enabled:
        t.donations_enabled = False
        t.business_type = _business_type(bool(t.sales_enabled), False)
        changes["donations_enabled"] = {"from": True, "to": False, "why": "commercial type"}
    return changes


# =================================================================== tenants: routes

@router.get("/meta")
def meta(admin: PlatformAdmin = Depends(pa.require_platform_admin)):
    return {
        "entity_types": [{"key": k, "label": v[0], "group": v[1], "primary_registration": v[2],
                          "primary_registration_label": entities.REG_LABELS.get(v[2]) if v[2] else None}
                         for k, v in entities.ENTITY_TYPES.items()],
        "verification_statuses": list(VERIFICATION),
    }


@router.get("/tenants")
def list_tenants(admin: PlatformAdmin = Depends(pa.require_platform_admin),
                 db: Session = Depends(pa.get_platform_db)):
    out = []
    for t in db.query(Tenant).order_by(Tenant.id).all():
        item = _tenant_out(t)
        item["stats"] = _stats(db, t.id)
        out.append(item)
    return out


class TenantCreate(IdentityIn):
    slug: str
    name: str
    entity_type: str = entities.DEFAULT_TYPE
    sales_enabled: bool = True
    donations_enabled: bool = False
    purchasing_enabled: bool = True
    inventory_enabled: bool = True
    vat_enabled: bool = True
    vat_rate: float = 15.0
    admin_username: str = "admin"
    admin_full_name: str = "مدير النظام"
    branch_name: str = "الفرع الرئيسي"


@router.post("/tenants", status_code=201)
def create_tenant(body: TenantCreate, request: Request,
                  admin: PlatformAdmin = Depends(pa.require_platform_admin),
                  db: Session = Depends(pa.get_platform_db)):
    slug = body.slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(status_code=400, detail="المعرّف: 3–50 حرفاً إنجليزياً صغيراً أو أرقاماً أو (-)")
    if db.query(Tenant).filter(Tenant.slug == slug).first():
        raise HTTPException(status_code=409, detail="المعرّف مستخدم لمنشأة أخرى")
    uname = body.admin_username.strip()
    if not USERNAME_RE.match(uname):
        raise HTTPException(status_code=400, detail="اسم مستخدم المدير: 3–50 حرفاً إنجليزياً أو أرقاماً")
    if not body.sales_enabled and not body.donations_enabled:
        raise HTTPException(status_code=400, detail="فعّل البيع أو التبرعات على الأقل")
    if body.donations_enabled and not entities.is_nonprofit(body.entity_type):
        raise HTTPException(status_code=400, detail="التبرعات متاحة للمنشآت غير الربحية فقط")

    ident = IdentityIn(**{k: getattr(body, k) for k in IdentityIn.model_fields})
    t = Tenant(slug=slug, name=body.name.strip(), entity_type=body.entity_type,
               sales_enabled=body.sales_enabled, donations_enabled=body.donations_enabled,
               purchasing_enabled=body.purchasing_enabled, inventory_enabled=body.inventory_enabled,
               vat_enabled=body.vat_enabled,
               business_type=_business_type(body.sales_enabled, body.donations_enabled),
               verification_status="verified", is_active=True)
    _apply_identity(db, t, None, ident)          # validates; raises before anything is written
    db.add(t)
    db.flush()
    _pin(db, t.id)
    db.add(TenantSettings(tenant_id=t.id, seller_name=t.name, vat_number=t.vat_number,
                          vat_rate=body.vat_rate, country="المملكة العربية السعودية",
                          country_en="Saudi Arabia"))
    temp = pa.temp_password()
    db.add(User(tenant_id=t.id, username=uname, password_hash=pwd.hash(temp),
                full_name=body.admin_full_name.strip() or "مدير النظام", role="admin",
                must_change_password=True))
    db.add(Location(tenant_id=t.id, name=body.branch_name.strip() or "الفرع الرئيسي"))
    pa.audit(db, request, "tenant_created", admin=admin, tenant=t,
             detail={"name": t.name, "entity_type": t.entity_type, "admin_username": uname,
                     "sales": t.sales_enabled, "donations": t.donations_enabled})
    db.commit()
    ensure_default_branch(db, t.id)              # adds the register to the new branch
    ensure_default_uom(db, t.id)
    _pin(db, None)
    return {"tenant": _tenant_out(t), "admin_username": uname, "temp_password": temp,
            "login_hint": "سيُطلب من المدير تغيير كلمة المرور عند أول دخول"}


@router.get("/tenants/{tid}")
def tenant_detail(tid: int, admin: PlatformAdmin = Depends(pa.require_platform_admin),
                  db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    st = _settings(db, tid)
    out = _tenant_out(t, st)
    _pin(db, tid)
    users = [{"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
              "is_active": bool(u.is_active), "must_change_password": bool(u.must_change_password)}
             for u in db.query(User).order_by(User.id).all()]
    locked = {r.username for r in db.execute(text(
        "SELECT username FROM login_attempts WHERE tenant_slug=:s AND locked_until > now()"),
        {"s": t.slug})}
    for u in users:
        u["locked"] = u["username"] in locked
    branches = []
    for loc in db.query(Location).order_by(Location.id).all():
        branches.append({"id": loc.id, "code": loc.code, "name": loc.name, "is_active": bool(loc.is_active),
                         "registers": db.query(Register).filter(Register.location_id == loc.id).count()})
    address = None
    if st:
        address = {k: getattr(st, k) for k in ("short_address", "building_number", "street_name",
                                               "additional_number", "district", "postal_code", "city",
                                               "region", "country")}
    _pin(db, None)
    out.update(stats=_stats(db, tid), users=users, branches=branches, address=address)
    out["can_delete"] = out["stats"]["documents"] == 0
    return out


@router.put("/tenants/{tid}/identity")
def update_identity(tid: int, body: IdentityIn, request: Request,
                    admin: PlatformAdmin = Depends(pa.require_platform_admin),
                    db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    st = _settings(db, tid)
    changes = _apply_identity(db, t, st, body)
    if changes:
        pa.audit(db, request, "identity_updated", admin=admin, tenant=t, detail=changes)
    db.commit()
    _pin(db, None)
    return _tenant_out(t, _settings(db, tid))


@router.put("/tenants/{tid}/capabilities")
def update_capabilities(tid: int, body: CapsIn, request: Request,
                        admin: PlatformAdmin = Depends(pa.require_platform_admin),
                        db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "verification_status" in data and data["verification_status"] not in VERIFICATION:
        raise HTTPException(status_code=400, detail="حالة التحقق غير معروفة")
    if data.get("donations_enabled") and not entities.is_nonprofit(t.entity_type):
        raise HTTPException(status_code=400, detail="التبرعات متاحة للمنشآت غير الربحية فقط")
    sales = data.get("sales_enabled", t.sales_enabled)
    don = data.get("donations_enabled", t.donations_enabled)
    if not sales and not don:
        raise HTTPException(status_code=400, detail="فعّل البيع أو التبرعات على الأقل")
    changes = {}
    for k, v in data.items():
        if getattr(t, k) != v:
            changes[k] = {"from": getattr(t, k), "to": v}
            setattr(t, k, v)
    t.business_type = _business_type(bool(t.sales_enabled), bool(t.donations_enabled))
    if changes:
        pa.audit(db, request, "capabilities_updated", admin=admin, tenant=t, detail=changes)
    db.commit()
    return _tenant_out(t, _settings(db, tid))


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


@router.post("/tenants/{tid}/suspend")
def suspend(tid: int, body: ReasonIn, request: Request,
            admin: PlatformAdmin = Depends(pa.require_platform_admin),
            db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    if not (body.reason or "").strip():
        raise HTTPException(status_code=400, detail="سبب الإيقاف مطلوب")
    t.is_active = False
    pa.audit(db, request, "tenant_suspended", admin=admin, tenant=t, detail={"reason": body.reason.strip()})
    db.commit()
    return _tenant_out(t)


@router.post("/tenants/{tid}/activate")
def activate(tid: int, request: Request, admin: PlatformAdmin = Depends(pa.require_platform_admin),
             db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    t.is_active = True
    pa.audit(db, request, "tenant_activated", admin=admin, tenant=t)
    db.commit()
    return _tenant_out(t)


@router.post("/tenants/{tid}/users/{uid}/reset-password")
def reset_user_password(tid: int, uid: int, request: Request,
                        admin: PlatformAdmin = Depends(pa.require_platform_admin),
                        db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    _pin(db, tid)
    u = db.query(User).filter(User.id == uid).first()
    if u is None:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    temp = pa.temp_password()
    u.password_hash = pwd.hash(temp)
    u.must_change_password = True
    u.is_active = True
    u.tokens_valid_after = _now()             # the user's open sessions end
    db.execute(text("UPDATE login_attempts SET failed_count=0, locked_until=NULL "
                    "WHERE tenant_slug=:s AND username=:u"), {"s": t.slug, "u": u.username})
    username = u.username
    pa.audit(db, request, "user_password_reset", admin=admin, tenant=t, target=username,
             detail={"role": u.role})
    db.commit()
    _pin(db, None)
    return {"username": username, "temp_password": temp}


class DeleteIn(BaseModel):
    confirm_slug: str


@router.delete("/tenants/{tid}")
def delete_tenant(tid: int, body: DeleteIn, request: Request,
                  admin: PlatformAdmin = Depends(pa.require_platform_admin),
                  db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    if body.confirm_slug.strip() != t.slug:
        raise HTTPException(status_code=400, detail="اكتب معرّف المنشأة للتأكيد")
    stats = _stats(db, tid)
    if stats["documents"] > 0:
        raise HTTPException(status_code=409, detail=(
            "لا يمكن حذف منشأة أصدرت مستندات (فواتير أو إشعارات دائنة أو إيصالات تبرع): "
            "يجب حفظها 6 سنوات على الأقل وفق متطلبات هيئة الزكاة والضريبة. استخدم الإيقاف بدلاً من الحذف."))
    snapshot = {"name": t.name, "entity_type": t.entity_type, "stats": stats}
    slug, ref = t.slug, t.id
    _pin(db, tid)
    db.execute(text("SELECT set_config('app.allow_purge', 'on', true)"))   # this transaction only
    db.execute(text("DELETE FROM login_attempts WHERE tenant_slug=:s"), {"s": slug})
    db.delete(t)
    db.flush()
    db.add(PlatformAuditLog(admin_id=admin.id, username=admin.username, action="tenant_deleted",
                            tenant_ref=ref, tenant_slug=slug, detail=snapshot, ip=pa.client_ip(request)))
    db.commit()
    _pin(db, None)
    return {"ok": True}


@router.get("/tenants/{tid}/activity")
def tenant_activity(tid: int, admin: PlatformAdmin = Depends(pa.require_platform_admin),
                    db: Session = Depends(pa.get_platform_db)):
    t = _get_tenant(db, tid)
    _pin(db, tid)
    tenant_log = [dict(r) for r in db.execute(text(
        "SELECT created_at, username, action, target, detail FROM tenant_audit_log "
        "ORDER BY id DESC LIMIT 50")).mappings()]
    daily = [dict(r) for r in db.execute(text("""
        SELECT d::date AS day,
               (SELECT count(*) FROM sales WHERE (issued_at AT TIME ZONE 'Asia/Riyadh')::date = d::date) AS sales,
               (SELECT coalesce(sum(total),0) FROM sales WHERE (issued_at AT TIME ZONE 'Asia/Riyadh')::date = d::date) AS sales_total,
               (SELECT count(*) FROM donations WHERE status='issued' AND (issued_at AT TIME ZONE 'Asia/Riyadh')::date = d::date) AS donations
        FROM generate_series((now() AT TIME ZONE 'Asia/Riyadh')::date - 13,
                             (now() AT TIME ZONE 'Asia/Riyadh')::date, interval '1 day') AS d
        ORDER BY d DESC""")).mappings()]
    _pin(db, None)
    platform_log = [_audit_out(a) for a in db.query(PlatformAuditLog)
                    .filter(PlatformAuditLog.tenant_ref == t.id)
                    .order_by(PlatformAuditLog.id.desc()).limit(50)]
    for r in tenant_log:
        r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
    for r in daily:
        r["day"] = r["day"].isoformat()
        r["sales_total"] = float(r["sales_total"])
    return {"daily": daily, "tenant_log": tenant_log, "platform_log": platform_log}


# =================================================================== audit

def _audit_out(a: PlatformAuditLog) -> dict:
    return {"id": a.id, "created_at": a.created_at.isoformat() if a.created_at else None,
            "username": a.username, "action": a.action, "tenant_ref": a.tenant_ref,
            "tenant_slug": a.tenant_slug, "target": a.target, "detail": a.detail, "ip": a.ip}


@router.get("/audit")
def audit_log(action: str | None = None, tenant: str | None = None, limit: int = 200,
              admin: PlatformAdmin = Depends(pa.require_platform_admin),
              db: Session = Depends(pa.get_platform_db)):
    q = db.query(PlatformAuditLog)
    if action:
        q = q.filter(PlatformAuditLog.action == action)
    if tenant:
        q = q.filter(PlatformAuditLog.tenant_slug == tenant)
    return [_audit_out(a) for a in q.order_by(PlatformAuditLog.id.desc()).limit(max(1, min(limit, 1000)))]
