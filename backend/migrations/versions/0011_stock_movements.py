"""Phase 5.3b: stock_movements ledger

Revision ID: 0011_stock_movements
Revises: 0010_uom
Create Date: 2026-08-11
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0011_stock_movements"
down_revision = "0010_uom"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("stock_movements"):
        op.create_table(
            "stock_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("type", sa.String(20), nullable=False),
            sa.Column("qty", sa.Numeric(14, 3), nullable=False),
            sa.Column("balance_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("unit_cost", sa.Numeric(14, 3), nullable=True),
            sa.Column("ref_type", sa.String(30), nullable=True),
            sa.Column("ref_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(300), nullable=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_stock_movements_tenant_id", "stock_movements", ["tenant_id"])
        op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])
        op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON stock_movements TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE stock_movements_id_seq TO {APP_ROLE}")
    op.execute("ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE stock_movements FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON stock_movements")
    op.execute(f"CREATE POLICY tenant_isolation ON stock_movements "
               f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON stock_movements")
    op.execute("ALTER TABLE stock_movements DISABLE ROW LEVEL SECURITY")
    op.drop_table("stock_movements")
