"""Phase 2: customers + sale.customer_id

Revision ID: 0005_customers
Revises: 0004_tenant_profile
Create Date: 2026-08-03

Idempotent (the Phase-0 baseline builds tables from live models via create_all).
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0005_customers"
down_revision = "0004_tenant_profile"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())

    if not insp.has_table("customers"):
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("phone", sa.String(30), nullable=True),
            sa.Column("email", sa.String(200), nullable=True),
            sa.Column("vat_number", sa.String(20), nullable=True),
            sa.Column("address", sa.String(300), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])
        op.create_index("ix_customers_phone", "customers", ["phone"])

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON customers TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE customers_id_seq TO {APP_ROLE}")
    op.execute("ALTER TABLE customers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE customers FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON customers")
    op.execute(f"CREATE POLICY tenant_isolation ON customers "
               f"USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")

    if "customer_id" not in [c["name"] for c in insp.get_columns("sales")]:
        op.add_column("sales", sa.Column("customer_id", sa.Integer(),
                                         sa.ForeignKey("customers.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("sales", "customer_id")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON customers")
    op.execute("ALTER TABLE customers DISABLE ROW LEVEL SECURITY")
    op.drop_table("customers")
