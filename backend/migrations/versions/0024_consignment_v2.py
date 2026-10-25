"""Consignment v2: consignor terms, barcoded items, status, returns.

Revision ID: 0024_consignment_v2
Revises: 0023_consignment
Create Date: 2026-09-13
"""
from alembic import op

revision = "0024_consignment_v2"
down_revision = "0023_consignment"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE consignors ADD COLUMN IF NOT EXISTS default_commission_percent double precision NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE consignors ADD COLUMN IF NOT EXISTS return_period_days integer NULL")
    op.execute("ALTER TABLE consignors ADD COLUMN IF NOT EXISTS payout_terms text NULL")
    op.execute("ALTER TABLE consignment_items ADD COLUMN IF NOT EXISTS barcode varchar(40) NULL")
    op.execute("ALTER TABLE consignment_items ADD COLUMN IF NOT EXISTS status varchar(12) NOT NULL DEFAULT 'active'")
    op.execute("ALTER TABLE consignment_items ADD COLUMN IF NOT EXISTS returned_qty numeric(12,3) NOT NULL DEFAULT 0")
    # backfill barcodes for existing items, then index for fast scan lookup
    op.execute("UPDATE consignment_items SET barcode = 'CN' || LPAD(id::text, 8, '0') WHERE barcode IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_consignment_items_barcode ON consignment_items(tenant_id, barcode)")

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_consignment_items_barcode")
    for c in ("returned_qty", "status", "barcode"):
        op.execute(f"ALTER TABLE consignment_items DROP COLUMN IF EXISTS {c}")
    for c in ("payout_terms", "return_period_days", "default_commission_percent"):
        op.execute(f"ALTER TABLE consignors DROP COLUMN IF EXISTS {c}")
