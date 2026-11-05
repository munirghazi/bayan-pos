"""Release 1 — ZATCA Phase 1 document engine.

One place for everything that makes an issued document legally stable:

* per-tenant, per-branch, per-document-type numbering with no gaps
  (``B01-INV-000001``, ``B01-CN-000001``, ``B01-DON-000001``) — the counter row
  is locked FOR UPDATE inside the issuing transaction, so a rollback also rolls
  the number back and two cashiers can never get the same number;
* the VAT snapshot — every line's rate, VAT and total is computed ONCE, with
  Decimal half-up rounding, and stored with the document (never recomputed);
* the seller snapshot (name, VAT number, national address) as of issue time;
* the Phase 1 QR (TLV tags 1-5, base64) built server-side;
* a per-branch hash chain (UUID + counter + previous hash) as Phase 2 groundwork.

NOTE on the hash: Phase 2 hashes are SHA-256 over the canonical UBL XML and the
chain restarts per EGS unit at onboarding. Until then this is an internal
tamper-evidence chain over a canonical JSON of the document.
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid as _uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import text

# ZATCA's specified PIH for the first document of a chain.
INITIAL_PIH = ("NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRk"
               "NGU5MWI0NjcyOWQ3M2EyN2YzNDkyMQ==")

DOC_INVOICE = "INV"
DOC_CREDIT_NOTE = "CN"
DOC_DONATION = "DON"
_DOC_TYPES = {DOC_INVOICE, DOC_CREDIT_NOTE, DOC_DONATION}

_C = Decimal("0.01")

SALE_PAYMENT_METHODS = {"cash", "card", "transfer"}
DONATION_PAYMENT_METHODS = {"card", "transfer"}      # donations never accept cash


# ---------------------------------------------------------------- money / time

def d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x if x is not None else 0))


def q2(x) -> Decimal:
    return d(x).quantize(_C, rounding=ROUND_HALF_UP)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_z(dt: datetime | None) -> str | None:
    """ISO-8601 in UTC with a 'Z' (naive values are treated as UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- branch

def resolve_location(db, register_id: int | None, user) -> tuple[int, int | None]:
    """Every document belongs to a branch. Register > user's branch > first branch."""
    from database import Register, Location
    if register_id is not None:
        reg = db.query(Register).filter(Register.id == register_id).first()
        if not reg:
            raise HTTPException(status_code=400, detail="الصندوق غير موجود")
        if getattr(user, "location_id", None) is not None and reg.location_id != user.location_id:
            raise HTTPException(status_code=403, detail="لا يمكنك العمل على صندوق خارج فرعك")
        return reg.location_id, reg.id
    if getattr(user, "location_id", None) is not None:
        return user.location_id, None
    loc = (db.query(Location).filter(Location.is_active == True)  # noqa: E712
             .order_by(Location.id).first()) or db.query(Location).order_by(Location.id).first()
    if loc is None:
        # A tenant created outside the normal path: give it its main branch now.
        loc = Location(name="الفرع الرئيسي")
        db.add(loc)
        db.flush()
        db.add(Register(location_id=loc.id, name="الصندوق 1"))
        db.flush()
    return loc.id, None


# ---------------------------------------------------------------- numbering

class Allocation:
    def __init__(self, location_id, doc_type, seq, number, previous_hash):
        self.location_id = location_id
        self.doc_type = doc_type
        self.seq = seq
        self.number = number
        self.previous_hash = previous_hash


def allocate(db, location_id: int, doc_type: str) -> Allocation:
    """Reserve the next number for (branch, doc type). Holds a row lock until commit."""
    assert doc_type in _DOC_TYPES
    db.execute(text(
        "INSERT INTO document_sequences (location_id, doc_type, last_value) "
        "VALUES (:l, :t, 0) ON CONFLICT DO NOTHING"), {"l": location_id, "t": doc_type})
    row = db.execute(text(
        "SELECT last_value, last_hash FROM document_sequences "
        "WHERE location_id = :l AND doc_type = :t FOR UPDATE"),
        {"l": location_id, "t": doc_type}).mappings().first()
    code = db.execute(text("SELECT code FROM locations WHERE id = :l"), {"l": location_id}).scalar()
    seq = int(row["last_value"]) + 1
    return Allocation(location_id, doc_type, seq, format_number(code, doc_type, seq),
                      row["last_hash"] or INITIAL_PIH)


def commit_allocation(db, alloc: Allocation, doc_hash: str | None) -> None:
    db.execute(text(
        "UPDATE document_sequences SET last_value = :s, last_hash = :h "
        "WHERE location_id = :l AND doc_type = :t"),
        {"s": alloc.seq, "h": doc_hash, "l": alloc.location_id, "t": alloc.doc_type})


def format_number(code: str, doc_type: str, seq: int) -> str:
    return f"{code}-{doc_type}-{seq:06d}"


# ---------------------------------------------------------------- seller

def seller_snapshot(db) -> dict:
    """Seller identity + VAT status at issue time (settings, onboarding fallback)."""
    from database import TenantSettings, Tenant
    st = db.query(TenantSettings).first()
    tid = st.tenant_id if st else None
    t = db.query(Tenant).filter(Tenant.id == tid).first() if tid else None

    def pick(field):
        v = getattr(st, field, None) if st else None
        return (v or "").strip() or None

    vat_number = pick("vat_number") or ((t.vat_number or "").strip() if t and t.vat_number else None)
    vat_enabled = bool(getattr(t, "vat_enabled", True)) if t else True
    rate = d(st.vat_rate if st and st.vat_rate is not None else 15)
    return {
        "name": pick("seller_name") or (t.name if t else None),
        "vat_number": vat_number,
        "vat_registered": bool(vat_enabled and vat_number),
        "vat_rate": float(rate) if vat_enabled else 0.0,
        "building_number": pick("building_number"),
        "street_name": pick("street_name"),
        "district": pick("district"),
        "city": pick("city"),
        "postal_code": pick("postal_code"),
        "additional_number": pick("additional_number"),
        "region": pick("region"),
        "country": pick("country"),
        "national_address": pick("national_address") or (t.national_address if t else None),
        "cr_number": (t.cr_number if t else None),
    }


# ---------------------------------------------------------------- VAT

def price_lines(lines: list[dict], seller: dict) -> tuple[list[dict], dict]:
    """Prices are VAT-inclusive. Each line: {price, quantity, is_tax_exempt, ...}.

    Returns (lines with vat_rate/line_total/line_vat, totals) — all Decimal.
    A seller that is not VAT-registered charges no VAT at all.
    """
    rate = d(seller["vat_rate"]) if seller["vat_registered"] else Decimal(0)
    out, total, vat, exempt = [], Decimal(0), Decimal(0), Decimal(0)
    for ln in lines:
        lt = q2(d(ln["price"]) * d(ln["quantity"]))
        r = Decimal(0) if ln.get("is_tax_exempt") else rate
        lv = q2(lt - lt / (1 + r / 100)) if r else Decimal(0)
        out.append({**ln, "vat_rate": r, "line_total": lt, "line_vat": lv})
        total += lt
        vat += lv
        if ln.get("is_tax_exempt") and seller["vat_registered"]:
            exempt += lt
    totals = {"total": q2(total), "vat_amount": q2(vat),
              "subtotal": q2(total - vat), "exempt_amount": q2(exempt)}
    return out, totals


# ---------------------------------------------------------------- QR / hash

def _tlv(tag: int, value: str) -> bytes:
    b = value.encode("utf-8")
    if len(b) > 255:
        b = b[:255]
    return bytes([tag, len(b)]) + b


def zatca_qr(seller_name: str, vat_number: str, issued_at: datetime,
             total, vat_amount) -> str:
    """Phase 1 QR: TLV tags 1-5, base64."""
    payload = (_tlv(1, seller_name or "") + _tlv(2, vat_number or "") +
               _tlv(3, iso_z(issued_at)) + _tlv(4, f"{q2(total):.2f}") +
               _tlv(5, f"{q2(vat_amount):.2f}"))
    return base64.b64encode(payload).decode("ascii")


def _jsonable(o):
    if isinstance(o, Decimal):
        return f"{o:.4f}"
    if isinstance(o, datetime):
        return iso_z(o)
    return str(o)


def document_hash(payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), default=_jsonable)
    return base64.b64encode(hashlib.sha256(canon.encode("utf-8")).digest()).decode("ascii")


def new_uuid() -> str:
    return str(_uuid.uuid4())


# ---------------------------------------------------------------- serialization

def money(x) -> float:
    return float(q2(x)) if x is not None else 0.0
