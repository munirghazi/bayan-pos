"""Phase 5.2: product master extension (barcode, cost_price, unit, reorder_level, default_supplier_id)

Revision ID: 0008_product_master
Revises: 0007_suppliers
Create Date: 2026-08-10

Idempotent (the Phase-0 baseline builds tables from live models via create_all).
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_product_master"
down_revision = "0007_suppliers"
branch_labels = None
depends_on = None

_COLUMNS = {
    "barcode": sa.Column("barcode", sa.String(64), nullable=True),
    "cost_price": sa.Column("cost_price", sa.Float(), nullable=False, server_default="0"),
    "unit": sa.Column("unit", sa.String(30), nullable=True),
    "reorder_level": sa.Column("reorder_level", sa.Integer(), nullable=False, server_default="0"),
    "default_supplier_id": sa.Column("default_supplier_id", sa.Integer(),
                                     sa.ForeignKey("suppliers.id"), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = [c["name"] for c in insp.get_columns("products")]
    for name, col in _COLUMNS.items():
        if name not in existing:
            op.add_column("products", col)
    idx_names = [i["name"] for i in insp.get_indexes("products")]
    if "ix_products_barcode" not in idx_names:
        op.create_index("ix_products_barcode", "products", ["barcode"])


def downgrade() -> None:
    for name in _COLUMNS:
        op.drop_column("products", name)
