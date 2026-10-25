"""Phase 1c white-label: receipt_footer (tenant) + show_powered_by (operator).

Revision ID: 0022_receipt_footer_powered_by
Revises: 0021_tenant_typography
Create Date: 2026-08-30
"""
from alembic import op

revision = "0022_receipt_footer_powered_by"
down_revision = "0021_tenant_typography"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS receipt_footer text NULL")
    op.execute("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS show_powered_by boolean NOT NULL DEFAULT true")

def downgrade() -> None:
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS receipt_footer")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS show_powered_by")
