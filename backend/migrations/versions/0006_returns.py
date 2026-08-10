"""Phase 2: returns + return_items (credit notes)

Revision ID: 0006_returns
Revises: 0005_customers
Create Date: 2026-08-05

Idempotent (the Phase-0 baseline builds tables from live models via create_all).
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0006_returns"
down_revision = "0005_customers"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"


def _rls(table):
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO {APP_ROLE}")
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} "
               f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    if not insp.has_table("returns"):
        op.create_table(
            "returns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("register_id", sa.Integer(), sa.ForeignKey("registers.id"), nullable=True),
            sa.Column("credit_note_number", sa.Integer(), nullable=False),
            sa.Column("total", sa.Float(), nullable=False),
            sa.Column("reason", sa.String(300), nullable=True),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_returns_tenant_id", "returns", ["tenant_id"])
        op.create_index("ix_returns_sale_id", "returns", ["sale_id"])

    if not insp.has_table("return_items"):
        op.create_table(
            "return_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("return_id", sa.Integer(),
                      sa.ForeignKey("returns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
        )
        op.create_index("ix_return_items_tenant_id", "return_items", ["tenant_id"])
        op.create_index("ix_return_items_return_id", "return_items", ["return_id"])

    _rls("returns")
    _rls("return_items")


def downgrade() -> None:
    for table in ("return_items", "returns"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
