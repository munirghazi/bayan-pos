"""Phase 5.4: purchase_orders + purchase_order_lines

Revision ID: 0013_purchase_orders
Revises: 0012_sale_item_uom
Create Date: 2026-08-12
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0013_purchase_orders"
down_revision = "0012_sale_item_uom"
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

    if not insp.has_table("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
            sa.Column("po_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("notes", sa.String(500), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"])
        op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"])

    if not insp.has_table("purchase_order_lines"):
        op.create_table(
            "purchase_order_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("po_id", sa.Integer(),
                      sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("uom_id", sa.Integer(), sa.ForeignKey("uoms.id"), nullable=True),
            sa.Column("unit_cost", sa.Numeric(14, 3), nullable=False, server_default="0"),
            sa.Column("received_qty", sa.Numeric(14, 3), nullable=False, server_default="0"),
        )
        op.create_index("ix_po_lines_tenant_id", "purchase_order_lines", ["tenant_id"])
        op.create_index("ix_po_lines_po_id", "purchase_order_lines", ["po_id"])

    _rls("purchase_orders")
    _rls("purchase_order_lines")


def downgrade() -> None:
    for table in ("purchase_order_lines", "purchase_orders"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
