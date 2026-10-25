"""Phase 1b white-label: font_family + ui_radius on tenant_settings.

Revision ID: 0021_tenant_typography
Revises: 0020_tenant_branding
Create Date: 2026-08-30
"""
from alembic import op

revision = "0021_tenant_typography"
down_revision = "0020_tenant_branding"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS font_family varchar(80) NULL")
    op.execute("ALTER TABLE tenant_settings ADD COLUMN IF NOT EXISTS ui_radius varchar(20) NULL")

def downgrade() -> None:
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS font_family")
    op.execute("ALTER TABLE tenant_settings DROP COLUMN IF EXISTS ui_radius")
