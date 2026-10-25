"""Consignment C: products.is_consignment (standalone consigned items).

Revision ID: 0025_product_is_consignment
Revises: 0024_consignment_v2
Create Date: 2026-09-14
"""
from alembic import op

revision = "0025_product_is_consignment"
down_revision = "0024_consignment_v2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_consignment boolean NOT NULL DEFAULT false")

def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS is_consignment")
