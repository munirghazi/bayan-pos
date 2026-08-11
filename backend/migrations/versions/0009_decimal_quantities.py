"""Phase 5.2b: decimal quantities (integer -> NUMERIC(14,3)) for UoM support

Revision ID: 0009_decimal_quantities
Revises: 0008_product_master
Create Date: 2026-08-10

Converts stock/quantity columns to NUMERIC(14,3) so fractional units (weight,
volume, fractional kit components) are exact. Idempotent: on a create_all
baseline the columns are already NUMERIC, and ALTER ... TYPE NUMERIC is a no-op.
"""
from alembic import op

revision = "0009_decimal_quantities"
down_revision = "0008_product_master"
branch_labels = None
depends_on = None

# (table, column)
_COLS = [
    ("products", "stock"),
    ("products", "reorder_level"),
    ("sale_items", "quantity"),
    ("return_items", "quantity"),
    ("kit_components", "quantity"),
]


def upgrade() -> None:
    for table, col in _COLS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE NUMERIC(14,3) "
            f"USING {col}::numeric"
        )


def downgrade() -> None:
    for table, col in _COLS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE INTEGER "
            f"USING round({col})::integer"
        )
