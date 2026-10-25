"""Phase 0: tenant business_type + capability flags + verification_status + docs

Revision ID: 0015_tenant_modes
Revises: 0014_goods_receipts
Create Date: 2026-08-17

Non-breaking: existing tenants default to business_type='mixed', all capabilities
enabled, verification_status='verified'. Each column is added in a single DDL
statement so the DEFAULT and NOT NULL are set together (raw inserts stay valid).
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_tenant_modes"
down_revision = "0014_goods_receipts"
branch_labels = None
depends_on = None

# name -> DDL (single statement guarantees DEFAULT + NOT NULL together)
_COLS = [
    ("national_address",   "ALTER TABLE tenants ADD COLUMN national_address varchar(50)"),
    ("license_number",     "ALTER TABLE tenants ADD COLUMN license_number varchar(50)"),
    ("business_type",      "ALTER TABLE tenants ADD COLUMN business_type varchar(20) NOT NULL DEFAULT 'mixed'"),
    ("sales_enabled",      "ALTER TABLE tenants ADD COLUMN sales_enabled boolean NOT NULL DEFAULT true"),
    ("donations_enabled",  "ALTER TABLE tenants ADD COLUMN donations_enabled boolean NOT NULL DEFAULT true"),
    ("purchasing_enabled", "ALTER TABLE tenants ADD COLUMN purchasing_enabled boolean NOT NULL DEFAULT true"),
    ("vat_enabled",        "ALTER TABLE tenants ADD COLUMN vat_enabled boolean NOT NULL DEFAULT true"),
    ("inventory_enabled",  "ALTER TABLE tenants ADD COLUMN inventory_enabled boolean NOT NULL DEFAULT true"),
    ("verification_status","ALTER TABLE tenants ADD COLUMN verification_status varchar(20) NOT NULL DEFAULT 'verified'"),
]


def upgrade() -> None:
    conn = op.get_bind()
    existing = [c["name"] for c in sa.inspect(conn).get_columns("tenants")]
    for name, ddl in _COLS:
        if name not in existing:
            conn.execute(sa.text(ddl))


def downgrade() -> None:
    for name, _ in _COLS:
        op.drop_column("tenants", name)
