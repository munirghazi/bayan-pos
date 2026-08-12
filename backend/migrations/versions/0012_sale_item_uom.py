"""Phase 5.3c: sale_items.uom_id (selling unit per line)

Revision ID: 0012_sale_item_uom
Revises: 0011_stock_movements
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_sale_item_uom"
down_revision = "0011_stock_movements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = [c["name"] for c in insp.get_columns("sale_items")]
    if "uom_id" not in cols:
        op.add_column("sale_items", sa.Column("uom_id", sa.Integer(),
                                              sa.ForeignKey("uoms.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("sale_items", "uom_id")
