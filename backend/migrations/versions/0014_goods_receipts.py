"""Phase 5.5: goods_receipts + goods_receipt_lines

Revision ID: 0014_goods_receipts
Revises: 0013_purchase_orders
Create Date: 2026-08-12
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0014_goods_receipts"
down_revision = "0013_purchase_orders"
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

    if not insp.has_table("goods_receipts"):
        op.create_table(
            "goods_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("po_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
            sa.Column("received_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_goods_receipts_tenant_id", "goods_receipts", ["tenant_id"])
        op.create_index("ix_goods_receipts_po_id", "goods_receipts", ["po_id"])

    if not insp.has_table("goods_receipt_lines"):
        op.create_table(
            "goods_receipt_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("receipt_id", sa.Integer(),
                      sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("po_line_id", sa.Integer(),
                      sa.ForeignKey("purchase_order_lines.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("qty_received", sa.Numeric(14, 3), nullable=False),
            sa.Column("base_qty", sa.Numeric(14, 3), nullable=False),
            sa.Column("unit_cost", sa.Numeric(14, 3), nullable=False, server_default="0"),
        )
        op.create_index("ix_gr_lines_tenant_id", "goods_receipt_lines", ["tenant_id"])
        op.create_index("ix_gr_lines_receipt_id", "goods_receipt_lines", ["receipt_id"])

    _rls("goods_receipts")
    _rls("goods_receipt_lines")


def downgrade() -> None:
    for table in ("goods_receipt_lines", "goods_receipts"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
