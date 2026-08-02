"""Baseline: multi-tenant schema + Row-Level Security isolation

Revision ID: 0001_baseline
Revises:
Create Date: 2026-07-31
"""
import os
from alembic import op

from database import Base, TENANT_SCOPED_TABLES

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Runtime application role (non-superuser, non-owner) that RLS applies to.
APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")

_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Create all tables from the SQLAlchemy metadata (baseline).
    Base.metadata.create_all(bind=bind)

    # 2) Grants for the application role.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
    )

    # 3) Row-Level Security on every tenant-scoped table.
    for tbl in TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        # Defence in depth: apply even if the app role were ever an owner.
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {tbl} "
            f"USING (tenant_id = {_GUC}) "
            f"WITH CHECK (tenant_id = {_GUC})"
        )


def downgrade() -> None:
    for tbl in TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
    Base.metadata.drop_all(bind=op.get_bind())
