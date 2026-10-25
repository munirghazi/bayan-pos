"""Consignment v1: consignors, intakes, consigned items, ledger, sale link.

Revision ID: 0023_consignment
Revises: 0022_receipt_footer_powered_by
Create Date: 2026-08-30
"""
import os
from alembic import op

revision = "0023_consignment"
down_revision = "0022_receipt_footer_powered_by"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"
_TABLES = ("consignors", "consignment_intakes", "consignment_items", "consignment_ledger")

def upgrade() -> None:
    op.execute(f"""CREATE TABLE IF NOT EXISTS consignors (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        name varchar(200) NOT NULL, phone varchar(30), email varchar(200),
        supplier_id integer REFERENCES suppliers(id) ON DELETE SET NULL,
        is_active boolean NOT NULL DEFAULT true,
        created_at timestamp DEFAULT now())""")
    op.execute(f"""CREATE TABLE IF NOT EXISTS consignment_intakes (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        consignor_id integer NOT NULL REFERENCES consignors(id) ON DELETE CASCADE,
        note text, created_at timestamp DEFAULT now())""")
    op.execute(f"""CREATE TABLE IF NOT EXISTS consignment_items (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        intake_id integer NOT NULL REFERENCES consignment_intakes(id) ON DELETE CASCADE,
        consignor_id integer NOT NULL REFERENCES consignors(id) ON DELETE CASCADE,
        product_id integer NOT NULL REFERENCES products(id),
        qty_received numeric(12,3) NOT NULL, qty_remaining numeric(12,3) NOT NULL,
        unit_price double precision NOT NULL,
        commission_percent double precision NOT NULL DEFAULT 0,
        created_at timestamp DEFAULT now())""")
    op.execute(f"""CREATE TABLE IF NOT EXISTS consignment_ledger (
        id serial PRIMARY KEY,
        tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
        consignor_id integer NOT NULL REFERENCES consignors(id) ON DELETE CASCADE,
        entry_type varchar(12) NOT NULL,
        sale_id integer REFERENCES sales(id),
        consignment_item_id integer REFERENCES consignment_items(id),
        amount double precision NOT NULL, note text,
        created_at timestamp DEFAULT now())""")
    op.execute("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS consignment_item_id integer REFERENCES consignment_items(id)")

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(_TABLES)} TO {APP_ROLE}")
    for t in _TABLES:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {t}_id_seq TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")

def downgrade() -> None:
    op.execute("ALTER TABLE sale_items DROP COLUMN IF EXISTS consignment_item_id")
    for t in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
