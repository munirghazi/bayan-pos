"""Kitting: is_kit flag + kit_components (bill-of-materials) with RLS

Revision ID: 0002_kitting
Revises: 0001_baseline
Create Date: 2026-07-31

Written idempotently: the baseline migration builds tables from the live
models via create_all, so on a FRESH database is_kit/kit_components may already
exist. On an EXISTING Phase-0 database they won't. This migration handles both.
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0002_kitting"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if "is_kit" not in [c["name"] for c in insp.get_columns("products")]:
        op.add_column("products",
                      sa.Column("is_kit", sa.Boolean(), nullable=False, server_default=sa.false()))

    if not insp.has_table("kit_components"):
        op.create_table(
            "kit_components",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("kit_product_id", sa.Integer(),
                      sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("component_product_id", sa.Integer(),
                      sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.UniqueConstraint("tenant_id", "kit_product_id", "component_product_id",
                                name="uq_kit_component"),
        )
        op.create_index("ix_kit_components_tenant_id", "kit_components", ["tenant_id"])
        op.create_index("ix_kit_components_kit_product_id", "kit_components", ["kit_product_id"])
        op.create_index("ix_kit_components_component_product_id", "kit_components",
                        ["component_product_id"])

    # Grants + RLS are safe to (re)apply.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON kit_components TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE kit_components_id_seq TO {APP_ROLE}")
    op.execute("ALTER TABLE kit_components ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE kit_components FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON kit_components")
    op.execute(
        f"CREATE POLICY tenant_isolation ON kit_components "
        f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON kit_components")
    op.execute("ALTER TABLE kit_components DISABLE ROW LEVEL SECURITY")
    op.drop_table("kit_components")
    op.drop_column("products", "is_kit")
