"""ZATCA structured national address on tenant_settings.

Revision ID: 0016_national_address
Revises: 0015_tenant_modes
Create Date: 2026-08-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_national_address"
down_revision = "0015_tenant_modes"
branch_labels = None
depends_on = None

_COLS = [
    ("building_number",   "ALTER TABLE tenant_settings ADD COLUMN building_number varchar(10)"),
    ("street_name",       "ALTER TABLE tenant_settings ADD COLUMN street_name varchar(150)"),
    ("district",          "ALTER TABLE tenant_settings ADD COLUMN district varchar(100)"),
    ("postal_code",       "ALTER TABLE tenant_settings ADD COLUMN postal_code varchar(10)"),
    ("additional_number", "ALTER TABLE tenant_settings ADD COLUMN additional_number varchar(10)"),
    ("region",            "ALTER TABLE tenant_settings ADD COLUMN region varchar(100)"),
]

def upgrade() -> None:
    conn = op.get_bind()
    existing = [c["name"] for c in sa.inspect(conn).get_columns("tenant_settings")]
    for name, ddl in _COLS:
        if name not in existing:
            conn.execute(sa.text(ddl))

def downgrade() -> None:
    for name, _ in _COLS:
        op.drop_column("tenant_settings", name)
