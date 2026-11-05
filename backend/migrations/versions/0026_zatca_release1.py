"""ZATCA Release 1: per-branch numbering, invoice/credit-note/donation snapshots,
money as numeric, issue timestamps with time zone, immutability of issued documents.

* locations.code (B01, B02 …) — auto-assigned per tenant, unique per tenant
* every tenant gets a default branch + register if it has none
* document_sequences — locked counter per (tenant, branch, doc type) + last hash
* sales / sale_items — invoice number, UUID, counter, hash chain, VAT snapshot,
  seller snapshot, QR, issued_at (timestamptz); money -> numeric
* returns / return_items — credit note number becomes text (B01-CN-000001),
  VAT snapshot, reference to the original invoice number
* donations — receipt number (B01-DON-000001), branch/register, void fields
* triggers: issued sales, credit notes and donations cannot be edited or deleted
  (donations: only PDPL anonymisation and a one-way void are allowed).
  A whole-tenant purge sets app.allow_purge='on' for its transaction.

Existing rows are back-filled deterministically (numbered per branch in date
order, VAT computed from the tenant's current rate) so nothing is lost.

Revision ID: 0026_zatca_release1
Revises: 0025_product_is_consignment
Create Date: 2026-11-05
"""
import base64
import hashlib
import json
import os
import uuid
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP

import sqlalchemy as sa
from alembic import op

revision = "0026_zatca_release1"
down_revision = "0025_product_is_consignment"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"
_RLS_TABLES = ("locations", "registers", "sales", "sale_items", "returns",
               "return_items", "donations", "tenant_settings", "products", "uoms")
INITIAL_PIH = ("NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRk"
               "NGU5MWI0NjcyOWQ3M2EyN2YzNDkyMQ==")
_C = Decimal("0.01")


# ----------------------------------------------------------------- helpers

def _q2(x):
    return Decimal(str(x if x is not None else 0)).quantize(_C, rounding=ROUND_HALF_UP)


def _iso(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tlv(tag, value):
    b = (value or "").encode("utf-8")[:255]
    return bytes([tag, len(b)]) + b


def _qr(name, vat, issued, total, vat_amount):
    return base64.b64encode(_tlv(1, name) + _tlv(2, vat) + _tlv(3, _iso(issued)) +
                            _tlv(4, f"{_q2(total):.2f}") + _tlv(5, f"{_q2(vat_amount):.2f}")).decode()


def _jsonable(o):
    if isinstance(o, Decimal):
        return f"{o:.4f}"
    if hasattr(o, "isoformat"):
        return _iso(o)
    return str(o)


def _hash(payload):
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), default=_jsonable)
    return base64.b64encode(hashlib.sha256(canon.encode()).digest()).decode()


def _rls_tables_present(bind):
    """The tables we touch whose RLS is currently FORCE'd (only those get toggled)."""
    rows = bind.execute(sa.text(
        "SELECT relname FROM pg_class WHERE relkind = 'r' AND relforcerowsecurity "
        "AND relnamespace = 'public'::regnamespace")).scalars().all()
    forced = set(rows)
    return [t for t in _RLS_TABLES if t in forced]


def _table_exists(bind, name):
    return name in set(sa.inspect(bind).get_table_names())


# ----------------------------------------------------------------- upgrade

def upgrade() -> None:
    bind = op.get_bind()
    rls = _rls_tables_present(bind)
    # The owner normally obeys FORCE'd RLS; lift it for this transaction only.
    for t in rls:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")

    # ---- 1. every tenant has a branch and a register
    op.execute("""INSERT INTO locations (tenant_id, name, is_active, created_at)
        SELECT t.id, 'الفرع الرئيسي', true, now() FROM tenants t
        WHERE NOT EXISTS (SELECT 1 FROM locations l WHERE l.tenant_id = t.id)""")
    op.execute("""INSERT INTO registers (tenant_id, location_id, name, is_active, created_at)
        SELECT l.tenant_id, l.id, 'الصندوق 1', true, now() FROM locations l
        WHERE l.id = (SELECT min(id) FROM locations x WHERE x.tenant_id = l.tenant_id)
          AND NOT EXISTS (SELECT 1 FROM registers r WHERE r.tenant_id = l.tenant_id)""")

    # ---- 2. branch codes
    op.execute("ALTER TABLE locations ADD COLUMN IF NOT EXISTS code varchar(10)")
    op.execute("""UPDATE locations l SET code = s.code FROM (
        SELECT id, 'B' || lpad(row_number() OVER (PARTITION BY tenant_id ORDER BY id)::text, 2, '0') AS code
        FROM locations) s WHERE s.id = l.id AND l.code IS NULL""")
    op.execute("ALTER TABLE locations ALTER COLUMN code SET NOT NULL")
    op.execute("ALTER TABLE locations ADD CONSTRAINT ck_location_code CHECK (code ~ '^[A-Z0-9]{1,6}$')")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_location_code ON locations (tenant_id, code)")
    op.execute("""CREATE OR REPLACE FUNCTION locations_assign_code() RETURNS trigger AS $$
        BEGIN
          IF NEW.code IS NULL OR NEW.code = '' THEN
            SELECT 'B' || lpad((COALESCE(max(substring(code FROM 2)::int), 0) + 1)::text, 2, '0')
              INTO NEW.code FROM locations
             WHERE tenant_id = NEW.tenant_id AND code ~ '^B[0-9]+$';
          ELSE
            NEW.code := upper(NEW.code);
          END IF;
          RETURN NEW;
        END $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_locations_code ON locations")
    op.execute("""CREATE TRIGGER trg_locations_code BEFORE INSERT ON locations
        FOR EACH ROW EXECUTE FUNCTION locations_assign_code()""")

    # ---- 3. document counters
    op.execute(f"""CREATE TABLE IF NOT EXISTS document_sequences (
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        location_id integer NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
        doc_type varchar(4) NOT NULL CHECK (doc_type IN ('INV','CN','DON')),
        last_value integer NOT NULL DEFAULT 0,
        last_hash varchar(100),
        PRIMARY KEY (tenant_id, location_id, doc_type))""")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON document_sequences TO {APP_ROLE}")
    op.execute("ALTER TABLE document_sequences ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON document_sequences")
    op.execute(f"CREATE POLICY tenant_isolation ON document_sequences "
               f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")

    # ---- 4. columns
    op.execute("""ALTER TABLE sales
        ADD COLUMN IF NOT EXISTS location_id integer REFERENCES locations(id),
        ADD COLUMN IF NOT EXISTS invoice_number varchar(30),
        ADD COLUMN IF NOT EXISTS invoice_seq integer,
        ADD COLUMN IF NOT EXISTS invoice_type varchar(12) NOT NULL DEFAULT 'simplified',
        ADD COLUMN IF NOT EXISTS is_tax_invoice boolean NOT NULL DEFAULT true,
        ADD COLUMN IF NOT EXISTS uuid uuid,
        ADD COLUMN IF NOT EXISTS previous_hash varchar(100),
        ADD COLUMN IF NOT EXISTS invoice_hash varchar(100),
        ADD COLUMN IF NOT EXISTS issued_at timestamptz,
        ADD COLUMN IF NOT EXISTS subtotal numeric(12,2),
        ADD COLUMN IF NOT EXISTS vat_amount numeric(12,2),
        ADD COLUMN IF NOT EXISTS exempt_amount numeric(12,2) NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS seller jsonb,
        ADD COLUMN IF NOT EXISTS qr_data text""")
    op.execute("ALTER TABLE sales ALTER COLUMN total TYPE numeric(12,2) USING round(total::numeric, 2)")
    op.execute("""ALTER TABLE sale_items
        ADD COLUMN IF NOT EXISTS product_name varchar(200),
        ADD COLUMN IF NOT EXISTS uom_name varchar(50),
        ADD COLUMN IF NOT EXISTS vat_rate numeric(5,2) NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS line_total numeric(12,2),
        ADD COLUMN IF NOT EXISTS line_vat numeric(12,2) NOT NULL DEFAULT 0""")
    op.execute("ALTER TABLE sale_items ALTER COLUMN price TYPE numeric(12,4) USING round(price::numeric, 4)")

    op.execute("ALTER TABLE returns ALTER COLUMN credit_note_number TYPE varchar(30) USING credit_note_number::text")
    op.execute("""ALTER TABLE returns
        ADD COLUMN IF NOT EXISTS location_id integer REFERENCES locations(id),
        ADD COLUMN IF NOT EXISTS credit_note_seq integer,
        ADD COLUMN IF NOT EXISTS original_invoice_number varchar(30),
        ADD COLUMN IF NOT EXISTS is_tax_invoice boolean NOT NULL DEFAULT true,
        ADD COLUMN IF NOT EXISTS uuid uuid,
        ADD COLUMN IF NOT EXISTS previous_hash varchar(100),
        ADD COLUMN IF NOT EXISTS invoice_hash varchar(100),
        ADD COLUMN IF NOT EXISTS issued_at timestamptz,
        ADD COLUMN IF NOT EXISTS subtotal numeric(12,2),
        ADD COLUMN IF NOT EXISTS vat_amount numeric(12,2),
        ADD COLUMN IF NOT EXISTS seller jsonb,
        ADD COLUMN IF NOT EXISTS qr_data text""")
    op.execute("ALTER TABLE returns ALTER COLUMN total TYPE numeric(12,2) USING round(total::numeric, 2)")
    op.execute("""ALTER TABLE return_items
        ADD COLUMN IF NOT EXISTS product_name varchar(200),
        ADD COLUMN IF NOT EXISTS vat_rate numeric(5,2) NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS line_total numeric(12,2),
        ADD COLUMN IF NOT EXISTS line_vat numeric(12,2) NOT NULL DEFAULT 0""")
    op.execute("ALTER TABLE return_items ALTER COLUMN price TYPE numeric(12,4) USING round(price::numeric, 4)")

    op.execute("""ALTER TABLE donations
        ADD COLUMN IF NOT EXISTS location_id integer REFERENCES locations(id),
        ADD COLUMN IF NOT EXISTS register_id integer REFERENCES registers(id),
        ADD COLUMN IF NOT EXISTS receipt_number varchar(30),
        ADD COLUMN IF NOT EXISTS receipt_seq integer,
        ADD COLUMN IF NOT EXISTS issued_at timestamptz,
        ADD COLUMN IF NOT EXISTS status varchar(10) NOT NULL DEFAULT 'issued',
        ADD COLUMN IF NOT EXISTS void_reason varchar(300),
        ADD COLUMN IF NOT EXISTS voided_at timestamptz,
        ADD COLUMN IF NOT EXISTS voided_by varchar(100)""")
    op.execute("ALTER TABLE donations ALTER COLUMN amount TYPE numeric(12,2) USING round(amount::numeric, 2)")
    op.execute("ALTER TABLE donations ALTER COLUMN payment_method DROP DEFAULT")

    # ---- 5. back-fill existing documents
    _backfill(bind)

    # ---- 6. constraints
    for stmt in (
        "ALTER TABLE sales ALTER COLUMN location_id SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN invoice_number SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN invoice_seq SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN uuid SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN invoice_hash SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN issued_at SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN subtotal SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN vat_amount SET NOT NULL",
        "ALTER TABLE sales ALTER COLUMN seller SET NOT NULL",
        "ALTER TABLE sale_items ALTER COLUMN line_total SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN location_id SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN credit_note_seq SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN uuid SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN invoice_hash SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN issued_at SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN subtotal SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN vat_amount SET NOT NULL",
        "ALTER TABLE returns ALTER COLUMN seller SET NOT NULL",
        "ALTER TABLE return_items ALTER COLUMN line_total SET NOT NULL",
        "ALTER TABLE donations ALTER COLUMN location_id SET NOT NULL",
        "ALTER TABLE donations ALTER COLUMN receipt_number SET NOT NULL",
        "ALTER TABLE donations ALTER COLUMN receipt_seq SET NOT NULL",
        "ALTER TABLE donations ALTER COLUMN issued_at SET NOT NULL",
        "ALTER TABLE donations ADD CONSTRAINT ck_donation_status CHECK (status IN ('issued','void'))",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_invoice_number ON sales (tenant_id, invoice_number)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_uuid ON sales (uuid)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_return_cn_number ON returns (tenant_id, credit_note_number)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_return_uuid ON returns (uuid)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_donation_receipt_number ON donations (tenant_id, receipt_number)",
        "CREATE INDEX IF NOT EXISTS ix_sales_issued_at ON sales (issued_at)",
        "CREATE INDEX IF NOT EXISTS ix_donations_issued_at ON donations (issued_at)",
    ):
        op.execute(stmt)

    # ---- 7. issued documents are immutable
    op.execute("""CREATE OR REPLACE FUNCTION forbid_document_change() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND current_setting('app.allow_purge', true) = 'on' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'issued document in % cannot be % (ZATCA: corrections only via credit/debit notes)',
                TG_TABLE_NAME, lower(TG_OP) USING ERRCODE = 'P0001';
        END $$ LANGUAGE plpgsql""")
    for t in ("sales", "sale_items", "returns", "return_items"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t}")
        op.execute(f"""CREATE TRIGGER trg_{t}_immutable BEFORE UPDATE OR DELETE ON {t}
            FOR EACH ROW EXECUTE FUNCTION forbid_document_change()""")

    op.execute("""CREATE OR REPLACE FUNCTION guard_donation_change() RETURNS trigger AS $$
        DECLARE allowed text[] := ARRAY['donor_name','note','status','void_reason','voided_at','voided_by'];
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF current_setting('app.allow_purge', true) = 'on' THEN RETURN OLD; END IF;
            RAISE EXCEPTION 'donation receipts cannot be deleted — void them instead' USING ERRCODE = 'P0001';
          END IF;
          IF (to_jsonb(OLD) - allowed) IS DISTINCT FROM (to_jsonb(NEW) - allowed) THEN
            RAISE EXCEPTION 'issued donation receipt cannot be edited' USING ERRCODE = 'P0001';
          END IF;
          IF OLD.status = 'void' AND NEW.status IS DISTINCT FROM 'void' THEN
            RAISE EXCEPTION 'a voided donation receipt cannot be reinstated' USING ERRCODE = 'P0001';
          END IF;
          IF OLD.status = 'void' AND (NEW.void_reason, NEW.voided_at, NEW.voided_by)
                IS DISTINCT FROM (OLD.void_reason, OLD.voided_at, OLD.voided_by) THEN
            RAISE EXCEPTION 'void details cannot be changed' USING ERRCODE = 'P0001';
          END IF;
          RETURN NEW;
        END $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_donations_guard ON donations")
    op.execute("""CREATE TRIGGER trg_donations_guard BEFORE UPDATE OR DELETE ON donations
        FOR EACH ROW EXECUTE FUNCTION guard_donation_change()""")

    for t in rls + ["document_sequences"]:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def _seller(row):
    vat = (row["s_vat"] or "").strip() or (row["t_vat"] or "").strip() or None
    registered = bool(row["vat_enabled"] and vat)
    return {
        "name": (row["seller_name"] or "").strip() or row["t_name"],
        "vat_number": vat, "vat_registered": registered,
        "vat_rate": float(row["vat_rate"] if row["vat_rate"] is not None else 15) if row["vat_enabled"] else 0.0,
        "building_number": row["building_number"], "street_name": row["street_name"],
        "district": row["district"], "city": row["city"], "postal_code": row["postal_code"],
        "additional_number": row["additional_number"], "region": row["region"],
        "country": row["country"],
        "national_address": row["national_address"] or row["t_addr"],
        "cr_number": row["cr_number"],
    }


def _backfill(bind):
    c = bind
    sellers = {}
    for r in c.execute(sa.text("""
        SELECT t.id AS tid, t.name AS t_name, t.vat_number AS t_vat, t.vat_enabled,
               t.national_address AS t_addr, t.cr_number,
               s.seller_name, s.vat_number AS s_vat, s.vat_rate, s.building_number, s.street_name,
               s.district, s.city, s.postal_code, s.additional_number, s.region, s.country,
               s.national_address
        FROM tenants t LEFT JOIN tenant_settings s ON s.tenant_id = t.id""")).mappings():
        sellers[r["tid"]] = _seller(r)

    codes = {r.id: r.code for r in c.execute(sa.text("SELECT id, code FROM locations"))}
    first_loc = {r.tenant_id: r.id for r in c.execute(sa.text(
        "SELECT tenant_id, min(id) AS id FROM locations GROUP BY tenant_id"))}
    reg_loc = {r.id: r.location_id for r in c.execute(sa.text("SELECT id, location_id FROM registers"))}
    chains = {}   # (tenant, location, doc) -> (seq, last_hash)

    def nxt(tid, loc, doc):
        seq, h = chains.get((tid, loc, doc), (0, INITIAL_PIH))
        return seq + 1, h

    # ---- sales
    sale_lines = {}
    for r in c.execute(sa.text("""
        SELECT si.id, si.sale_id, si.price, si.quantity, si.is_tax_exempt,
               p.name AS pname, u.name AS uname
        FROM sale_items si LEFT JOIN products p ON p.id = si.product_id
        LEFT JOIN uoms u ON u.id = si.uom_id ORDER BY si.id""")).mappings():
        sale_lines.setdefault(r["sale_id"], []).append(r)

    sale_info = {}   # sale_id -> (number, {product_id_line_id: rate})
    for s in c.execute(sa.text(
            "SELECT id, tenant_id, register_id, created_at FROM sales "
            "ORDER BY tenant_id, created_at, id")).mappings():
        tid = s["tenant_id"]
        seller = sellers[tid]
        loc = reg_loc.get(s["register_id"]) or first_loc[tid]
        seq, prev = nxt(tid, loc, "INV")
        number = f"{codes[loc]}-INV-{seq:06d}"
        issued = s["created_at"].replace(tzinfo=timezone.utc)
        rate_all = Decimal(str(seller["vat_rate"])) if seller["vat_registered"] else Decimal(0)
        total = vat = exempt = Decimal(0)
        lines_out = []
        for ln in sale_lines.get(s["id"], []):
            lt = _q2(Decimal(str(ln["price"])) * Decimal(str(ln["quantity"])))
            rate = Decimal(0) if ln["is_tax_exempt"] else rate_all
            lv = _q2(lt - lt / (1 + rate / 100)) if rate else Decimal(0)
            total += lt
            vat += lv
            if ln["is_tax_exempt"] and seller["vat_registered"]:
                exempt += lt
            c.execute(sa.text("""UPDATE sale_items SET product_name = :n, uom_name = :u,
                vat_rate = :r, line_total = :t, line_vat = :v WHERE id = :i"""),
                {"n": ln["pname"], "u": ln["uname"], "r": rate, "t": lt, "v": lv, "i": ln["id"]})
            lines_out.append({"name": ln["pname"], "qty": Decimal(str(ln["quantity"])),
                              "price": Decimal(str(ln["price"])), "vat": lv})
        total, vat = _q2(total), _q2(vat)
        uid = str(uuid.uuid4())
        h = _hash({"type": "INV", "number": number, "uuid": uid, "icv": seq, "pih": prev,
                   "issued_at": issued, "seller_vat": seller["vat_number"],
                   "total": total, "vat": vat, "lines": lines_out})
        qr = (_qr(seller["name"], seller["vat_number"], issued, total, vat)
              if seller["vat_registered"] else None)
        c.execute(sa.text("""UPDATE sales SET location_id = :loc, invoice_number = :num,
            invoice_seq = :seq, is_tax_invoice = :tax, uuid = CAST(:uid AS uuid), previous_hash = :prev,
            invoice_hash = :h, issued_at = :iss, total = :tot, subtotal = :sub, vat_amount = :vat,
            exempt_amount = :ex, seller = CAST(:seller AS jsonb), qr_data = :qr WHERE id = :id"""),
            {"loc": loc, "num": number, "seq": seq, "tax": seller["vat_registered"], "uid": uid,
             "prev": prev, "h": h, "iss": issued, "tot": total, "sub": total - vat, "vat": vat,
             "ex": _q2(exempt), "seller": json.dumps(seller, ensure_ascii=False), "qr": qr, "id": s["id"]})
        chains[(tid, loc, "INV")] = (seq, h)
        sale_info[s["id"]] = (number, loc, {ln["id"]: None for ln in sale_lines.get(s["id"], [])})

    # ---- returns / credit notes (numbered in the original invoice's branch)
    sale_rates = {}
    for r in c.execute(sa.text("SELECT sale_id, product_id, vat_rate FROM sale_items")).mappings():
        sale_rates[(r["sale_id"], r["product_id"])] = Decimal(str(r["vat_rate"]))
    ret_lines = {}
    for r in c.execute(sa.text("""SELECT ri.id, ri.return_id, ri.product_id, ri.price, ri.quantity,
            p.name AS pname FROM return_items ri LEFT JOIN products p ON p.id = ri.product_id
            ORDER BY ri.id""")).mappings():
        ret_lines.setdefault(r["return_id"], []).append(r)
    for rt in c.execute(sa.text(
            "SELECT id, tenant_id, sale_id, created_at FROM returns ORDER BY tenant_id, created_at, id")).mappings():
        tid = rt["tenant_id"]
        seller = sellers[tid]
        inv_number, loc, _ = sale_info[rt["sale_id"]]
        seq, prev = nxt(tid, loc, "CN")
        number = f"{codes[loc]}-CN-{seq:06d}"
        issued = rt["created_at"].replace(tzinfo=timezone.utc)
        total = vat = Decimal(0)
        lines_out = []
        for ln in ret_lines.get(rt["id"], []):
            rate = sale_rates.get((rt["sale_id"], ln["product_id"]), Decimal(0))
            lt = _q2(Decimal(str(ln["price"])) * Decimal(str(ln["quantity"])))
            lv = _q2(lt - lt / (1 + rate / 100)) if rate else Decimal(0)
            total += lt
            vat += lv
            c.execute(sa.text("""UPDATE return_items SET product_name = :n, vat_rate = :r,
                line_total = :t, line_vat = :v WHERE id = :i"""),
                {"n": ln["pname"], "r": rate, "t": lt, "v": lv, "i": ln["id"]})
            lines_out.append({"name": ln["pname"], "qty": Decimal(str(ln["quantity"])),
                              "price": Decimal(str(ln["price"])), "vat": lv})
        total, vat = _q2(total), _q2(vat)
        uid = str(uuid.uuid4())
        h = _hash({"type": "CN", "number": number, "uuid": uid, "icv": seq, "pih": prev,
                   "issued_at": issued, "ref": inv_number, "seller_vat": seller["vat_number"],
                   "total": total, "vat": vat, "lines": lines_out})
        qr = (_qr(seller["name"], seller["vat_number"], issued, total, vat)
              if seller["vat_registered"] else None)
        c.execute(sa.text("""UPDATE returns SET location_id = :loc, credit_note_number = :num,
            credit_note_seq = :seq, original_invoice_number = :ref, is_tax_invoice = :tax,
            uuid = CAST(:uid AS uuid), previous_hash = :prev, invoice_hash = :h, issued_at = :iss,
            total = :tot, subtotal = :sub, vat_amount = :vat, seller = CAST(:seller AS jsonb),
            qr_data = :qr WHERE id = :id"""),
            {"loc": loc, "num": number, "seq": seq, "ref": inv_number, "tax": seller["vat_registered"],
             "uid": uid, "prev": prev, "h": h, "iss": issued, "tot": total, "sub": total - vat,
             "vat": vat, "seller": json.dumps(seller, ensure_ascii=False), "qr": qr, "id": rt["id"]})
        chains[(tid, loc, "CN")] = (seq, h)

    # ---- donations (receipts — no VAT, no QR)
    for dn in c.execute(sa.text(
            "SELECT id, tenant_id, created_at FROM donations ORDER BY tenant_id, created_at, id")).mappings():
        tid = dn["tenant_id"]
        loc = first_loc[tid]
        seq, _ = nxt(tid, loc, "DON")
        c.execute(sa.text("""UPDATE donations SET location_id = :loc, receipt_number = :num,
            receipt_seq = :seq, issued_at = :iss WHERE id = :id"""),
            {"loc": loc, "num": f"{codes[loc]}-DON-{seq:06d}", "seq": seq,
             "iss": dn["created_at"].replace(tzinfo=timezone.utc), "id": dn["id"]})
        chains[(tid, loc, "DON")] = (seq, None)

    for (tid, loc, doc), (seq, h) in chains.items():
        c.execute(sa.text("""INSERT INTO document_sequences (tenant_id, location_id, doc_type, last_value, last_hash)
            VALUES (:t, :l, :d, :s, :h)"""), {"t": tid, "l": loc, "d": doc, "s": seq, "h": h})


# ----------------------------------------------------------------- downgrade

def downgrade() -> None:
    bind = op.get_bind()
    rls = _rls_tables_present(bind)
    for t in ("sales", "sale_items", "returns", "return_items"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t}")
    op.execute("DROP TRIGGER IF EXISTS trg_donations_guard ON donations")
    op.execute("DROP FUNCTION IF EXISTS forbid_document_change()")
    op.execute("DROP FUNCTION IF EXISTS guard_donation_change()")
    for t in rls:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")

    op.execute("ALTER TABLE donations DROP CONSTRAINT IF EXISTS ck_donation_status")
    op.execute("""ALTER TABLE donations DROP COLUMN IF EXISTS location_id, DROP COLUMN IF EXISTS register_id,
        DROP COLUMN IF EXISTS receipt_number, DROP COLUMN IF EXISTS receipt_seq,
        DROP COLUMN IF EXISTS issued_at, DROP COLUMN IF EXISTS status, DROP COLUMN IF EXISTS void_reason,
        DROP COLUMN IF EXISTS voided_at, DROP COLUMN IF EXISTS voided_by""")
    op.execute("ALTER TABLE donations ALTER COLUMN amount TYPE double precision")
    op.execute("ALTER TABLE donations ALTER COLUMN payment_method SET DEFAULT 'cash'")

    op.execute("""ALTER TABLE return_items DROP COLUMN IF EXISTS product_name, DROP COLUMN IF EXISTS vat_rate,
        DROP COLUMN IF EXISTS line_total, DROP COLUMN IF EXISTS line_vat""")
    op.execute("ALTER TABLE return_items ALTER COLUMN price TYPE double precision")
    op.execute("DROP INDEX IF EXISTS uq_return_cn_number")
    op.execute("DROP INDEX IF EXISTS uq_return_uuid")
    op.execute("""ALTER TABLE returns ALTER COLUMN credit_note_number TYPE integer
        USING COALESCE(credit_note_seq, NULLIF(regexp_replace(credit_note_number, '\\D', '', 'g'), '')::integer, 0)""")
    op.execute("""ALTER TABLE returns DROP COLUMN IF EXISTS location_id, DROP COLUMN IF EXISTS credit_note_seq,
        DROP COLUMN IF EXISTS original_invoice_number, DROP COLUMN IF EXISTS is_tax_invoice,
        DROP COLUMN IF EXISTS uuid, DROP COLUMN IF EXISTS previous_hash, DROP COLUMN IF EXISTS invoice_hash,
        DROP COLUMN IF EXISTS issued_at, DROP COLUMN IF EXISTS subtotal, DROP COLUMN IF EXISTS vat_amount,
        DROP COLUMN IF EXISTS seller, DROP COLUMN IF EXISTS qr_data""")
    op.execute("ALTER TABLE returns ALTER COLUMN total TYPE double precision")

    op.execute("""ALTER TABLE sale_items DROP COLUMN IF EXISTS product_name, DROP COLUMN IF EXISTS uom_name,
        DROP COLUMN IF EXISTS vat_rate, DROP COLUMN IF EXISTS line_total, DROP COLUMN IF EXISTS line_vat""")
    op.execute("ALTER TABLE sale_items ALTER COLUMN price TYPE double precision")
    op.execute("DROP INDEX IF EXISTS uq_sale_invoice_number")
    op.execute("DROP INDEX IF EXISTS uq_sale_uuid")
    op.execute("DROP INDEX IF EXISTS ix_sales_issued_at")
    op.execute("DROP INDEX IF EXISTS ix_donations_issued_at")
    op.execute("""ALTER TABLE sales DROP COLUMN IF EXISTS location_id, DROP COLUMN IF EXISTS invoice_number,
        DROP COLUMN IF EXISTS invoice_seq, DROP COLUMN IF EXISTS invoice_type, DROP COLUMN IF EXISTS is_tax_invoice,
        DROP COLUMN IF EXISTS uuid, DROP COLUMN IF EXISTS previous_hash, DROP COLUMN IF EXISTS invoice_hash,
        DROP COLUMN IF EXISTS issued_at, DROP COLUMN IF EXISTS subtotal, DROP COLUMN IF EXISTS vat_amount,
        DROP COLUMN IF EXISTS exempt_amount, DROP COLUMN IF EXISTS seller, DROP COLUMN IF EXISTS qr_data""")
    op.execute("ALTER TABLE sales ALTER COLUMN total TYPE double precision")

    op.execute("DROP TABLE IF EXISTS document_sequences")
    op.execute("DROP TRIGGER IF EXISTS trg_locations_code ON locations")
    op.execute("DROP FUNCTION IF EXISTS locations_assign_code()")
    op.execute("DROP INDEX IF EXISTS uq_location_code")
    op.execute("ALTER TABLE locations DROP CONSTRAINT IF EXISTS ck_location_code")
    op.execute("ALTER TABLE locations DROP COLUMN IF EXISTS code")
    # default branches/registers created by upgrade are left in place (harmless).
    for t in rls:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
