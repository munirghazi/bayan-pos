"""Phase 1 white-label: tenant_settings branding fields.

Revision ID: 0020_tenant_branding
Revises: 0019_pdpl_privacy
Create Date: 2026-08-28
"""
from alembic import op

revision = "0020_tenant_branding"
down_revision = "0019_pdpl_privacy"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS favicon_url varchar(500) NULL")
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS primary_color varchar(9) NULL")
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS accent_color varchar(9) NULL")
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS brand_name varchar(120) NULL")

def downgrade() -> None:
    for col in ("favicon_url", "primary_color", "accent_color", "brand_name"):
        op.execute(f"ALTER TABLE tenant_settings DROP COLUMN IF EXISTS {col}")
