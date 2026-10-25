"""Wave 2: register_closings (end-of-day / Z-report).

Revision ID: 0018_register_closings
Revises: 0017_security_hardening
Create Date: 2026-08-25
"""
import os
from alembic import op

revision = "0018_register_closings"
down_revision = "0017_security_hardening"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"

def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS register_closings (
            id serial PRIMARY KEY,
            tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
            register_id integer NOT NULL REFERENCES registers(id) ON DELETE CASCADE,
            opened_at timestamp NULL,
            closed_at timestamp NOT NULL DEFAULT now(),
            closed_by varchar(100) NULL,
            opening_float double precision NOT NULL DEFAULT 0,
            sales_count integer NOT NULL DEFAULT 0,
            total_sales double precision NOT NULL DEFAULT 0,
            cash_sales double precision NOT NULL DEFAULT 0,
            card_sales double precision NOT NULL DEFAULT 0,
            transfer_sales double precision NOT NULL DEFAULT 0,
            other_sales double precision NOT NULL DEFAULT 0,
            expected_cash double precision NOT NULL DEFAULT 0,
            counted_cash double precision NOT NULL DEFAULT 0,
            variance double precision NOT NULL DEFAULT 0,
            note text NULL
        )""")
    op.execute(f"CREATE INDEX IF NOT EXISTS ix_reg_closings_register ON register_closings(register_id)")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON register_closings TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE register_closings_id_seq TO {APP_ROLE}")
    op.execute("ALTER TABLE register_closings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE register_closings FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON register_closings")
    op.execute(f"CREATE POLICY tenant_isolation ON register_closings USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")

def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON register_closings")
    op.execute("DROP TABLE IF EXISTS register_closings")
