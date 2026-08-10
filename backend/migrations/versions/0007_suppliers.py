"""Phase 5.1: suppliers + supplier_documents (vendor master + compliance docs)

Revision ID: 0007_suppliers
Revises: 0006_returns
Create Date: 2026-08-10

Idempotent (the Phase-0 baseline builds tables from live models via create_all).
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0007_suppliers"
down_revision = "0006_returns"
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

    if not insp.has_table("suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("iban", sa.String(34), nullable=True),
            sa.Column("payment_terms", sa.String(100), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"])

    if not insp.has_table("supplier_documents"):
        op.create_table(
            "supplier_documents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("supplier_id", sa.Integer(),
                      sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("doc_type", sa.String(30), nullable=False),
            sa.Column("number", sa.String(100), nullable=True),
            sa.Column("issue_date", sa.Date(), nullable=True),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("file_url", sa.String(500), nullable=True),
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime()),
            sa.UniqueConstraint("supplier_id", "doc_type", name="uq_supplier_doc_type"),
        )
        op.create_index("ix_supplier_documents_tenant_id", "supplier_documents", ["tenant_id"])
        op.create_index("ix_supplier_documents_supplier_id", "supplier_documents", ["supplier_id"])

    _rls("suppliers")
    _rls("supplier_documents")


def downgrade() -> None:
    for table in ("supplier_documents", "suppliers"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
