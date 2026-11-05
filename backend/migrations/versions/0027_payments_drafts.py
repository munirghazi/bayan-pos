"""Release 1.1: split payments, transfer proofs, drafts, refund method.

* payment_proofs   — uploaded bank-transfer proofs (private storage), single use
* sale_payments    — one row per tender on an invoice (cash / card / transfer);
                     existing sales are back-filled with one row each; immutable
* sales.change_given — change returned from cash
* returns.refund_method — how the credit note was refunded (back-filled)
* donations.proof_id — transfer proof of a donation
* pos_drafts       — a sale / donation waiting for its transfer proof: no number,
                     no QR, stock reserved; issued or cancelled (auto at day end)
* tenant_settings.require_transfer_proof (default true)
* register_closings.cash_refunds

Revision ID: 0027_payments_drafts
Revises: 0026_zatca_release1
Create Date: 2026-11-05
"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0027_payments_drafts"
down_revision = "0026_zatca_release1"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"
_NEW = ("payment_proofs", "sale_payments", "pos_drafts")
_TOUCH = ("sales", "returns", "donations", "tenant_settings", "register_closings")


def _forced(bind, tables):
    rows = bind.execute(sa.text(
        "SELECT relname FROM pg_class WHERE relkind='r' AND relforcerowsecurity "
        "AND relnamespace='public'::regnamespace")).scalars().all()
    return [t for t in tables if t in set(rows)]


def _rls(table):
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} "
               f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")


def upgrade() -> None:
    bind = op.get_bind()
    forced = _forced(bind, _TOUCH)
    for t in forced:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")

    op.execute(f"""CREATE TABLE IF NOT EXISTS payment_proofs (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        stored_name varchar(80) NOT NULL,
        original_name varchar(200),
        mime varchar(60) NOT NULL,
        size_bytes integer NOT NULL,
        sha256 varchar(64) NOT NULL,
        uploaded_by integer REFERENCES users(id),
        used boolean NOT NULL DEFAULT false,
        used_ref varchar(40),
        created_at timestamptz NOT NULL DEFAULT now())""")

    op.execute(f"""CREATE TABLE IF NOT EXISTS sale_payments (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        sale_id integer NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
        method varchar(20) NOT NULL CHECK (method IN ('cash','card','transfer')),
        amount numeric(12,2) NOT NULL CHECK (amount > 0),
        tendered numeric(12,2),
        card_ref varchar(100),
        proof_id integer REFERENCES payment_proofs(id),
        created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_payments_sale ON sale_payments (sale_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_sale_payment_proof ON sale_payments (proof_id) "
               "WHERE proof_id IS NOT NULL")

    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS change_given numeric(12,2) NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE returns ADD COLUMN IF NOT EXISTS refund_method varchar(20)")
    op.execute("ALTER TABLE donations ADD COLUMN IF NOT EXISTS proof_id integer REFERENCES payment_proofs(id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_donation_proof ON donations (proof_id) "
               "WHERE proof_id IS NOT NULL")
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS require_transfer_proof "
               "boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE register_closings ADD COLUMN IF NOT EXISTS cash_refunds "
               "double precision NOT NULL DEFAULT 0")

    op.execute(f"""CREATE TABLE IF NOT EXISTS pos_drafts (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        kind varchar(10) NOT NULL CHECK (kind IN ('sale','donation')),
        status varchar(10) NOT NULL DEFAULT 'open' CHECK (status IN ('open','issued','cancelled')),
        location_id integer NOT NULL REFERENCES locations(id),
        register_id integer REFERENCES registers(id),
        user_id integer NOT NULL REFERENCES users(id),
        payload jsonb NOT NULL,
        total numeric(12,2) NOT NULL,
        customer_label varchar(200),
        issued_ref varchar(30),
        cancel_reason varchar(200),
        created_at timestamptz NOT NULL DEFAULT now(),
        closed_at timestamptz)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pos_drafts_open ON pos_drafts (status, created_at)")

    # ---- back-fill: one payment row per existing invoice; refund method of credit notes
    op.execute("""INSERT INTO sale_payments (tenant_id, sale_id, method, amount, tendered, card_ref, created_at)
        SELECT s.tenant_id, s.id,
               CASE WHEN s.payment_method IN ('cash','card','transfer') THEN s.payment_method ELSE 'cash' END,
               s.total, CASE WHEN s.payment_method = 'cash' THEN s.total END, s.card_ref, s.issued_at
        FROM sales s
        WHERE s.total > 0 AND NOT EXISTS (SELECT 1 FROM sale_payments p WHERE p.sale_id = s.id)""")
    op.execute("ALTER TABLE returns DISABLE TRIGGER trg_returns_immutable")
    op.execute("""UPDATE returns r SET refund_method = COALESCE(
            (SELECT CASE WHEN s.payment_method IN ('cash','card','transfer') THEN s.payment_method ELSE 'cash' END
             FROM sales s WHERE s.id = r.sale_id), 'cash')
        WHERE r.refund_method IS NULL""")
    op.execute("ALTER TABLE returns ENABLE TRIGGER trg_returns_immutable")

    # RLS on the new tables only AFTER the back-fill (the owner obeys FORCE'd RLS)
    for t in _NEW:
        _rls(t)
    op.execute(f"REVOKE UPDATE ON sale_payments FROM {APP_ROLE}")

    # payment rows are part of the issued invoice: never edited or deleted
    op.execute("DROP TRIGGER IF EXISTS trg_sale_payments_immutable ON sale_payments")
    op.execute("""CREATE TRIGGER trg_sale_payments_immutable BEFORE UPDATE OR DELETE ON sale_payments
        FOR EACH ROW EXECUTE FUNCTION forbid_document_change()""")
    for t in forced:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    bind = op.get_bind()
    forced = _forced(bind, _TOUCH)
    for t in forced:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS pos_drafts")
    op.execute("DROP TABLE IF EXISTS sale_payments")
    op.execute("DROP INDEX IF EXISTS uq_donation_proof")
    op.execute("ALTER TABLE donations DROP COLUMN IF EXISTS proof_id")
    op.execute("DROP TABLE IF EXISTS payment_proofs")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS change_given")
    op.execute("ALTER TABLE returns DROP COLUMN IF EXISTS refund_method")
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS require_transfer_proof")
    op.execute("ALTER TABLE register_closings DROP COLUMN IF EXISTS cash_refunds")
    for t in forced:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
