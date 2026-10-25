"""Wave 3 (PDPL): customers.erased_at + tenant_settings.data_retention_months.

Revision ID: 0019_pdpl_privacy
Revises: 0018_register_closings
Create Date: 2026-08-26
"""
from alembic import op

revision = "0019_pdpl_privacy"
down_revision = "0018_register_closings"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS erased_at timestamp NULL")
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS data_retention_months integer NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS data_retention_months")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS erased_at")
