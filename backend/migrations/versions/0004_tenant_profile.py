"""Per-tenant settings: city, country, website, logo_url

Revision ID: 0004_tenant_profile
Revises: 0003_locations
Create Date: 2026-08-03

Idempotent (the Phase-0 baseline builds tables from live models via create_all).
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_tenant_profile"
down_revision = "0003_locations"
branch_labels = None
depends_on = None

_COLUMNS = {
    "city": sa.Column("city", sa.String(100), nullable=True),
    "country": sa.Column("country", sa.String(100), nullable=True),
    "website": sa.Column("website", sa.String(200), nullable=True),
    "logo_url": sa.Column("logo_url", sa.String(500), nullable=True),
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existing = [c["name"] for c in insp.get_columns("tenant_settings")]
    for name, col in _COLUMNS.items():
        if name not in existing:
            op.add_column("tenant_settings", col)


def downgrade() -> None:
    for name in _COLUMNS:
        op.drop_column("tenant_settings", name)
