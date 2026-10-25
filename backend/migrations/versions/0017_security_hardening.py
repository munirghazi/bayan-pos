"""Wave 1 security & integrity: login_attempts, idempotency_keys, tenant_audit_log.

Revision ID: 0017_security_hardening
Revises: 0016_national_address
Create Date: 2026-08-25
"""
import os
from alembic import op
import sqlalchemy as sa

revision = "0017_security_hardening"
down_revision = "0016_national_address"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"
_TENANT_TABLES = ("idempotency_keys", "tenant_audit_log")

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id serial PRIMARY KEY,
            tenant_slug varchar(63) NOT NULL,
            username varchar(100) NOT NULL,
            failed_count integer NOT NULL DEFAULT 0,
            locked_until timestamp NULL,
            updated_at timestamp DEFAULT now(),
            CONSTRAINT uq_login_attempt UNIQUE (tenant_slug, username)
        )""")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            id serial PRIMARY KEY,
            tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
            idem_key varchar(120) NOT NULL,
            endpoint varchar(60) NOT NULL,
            response_json text NOT NULL,
            created_at timestamp DEFAULT now(),
            CONSTRAINT uq_idem UNIQUE (tenant_id, idem_key, endpoint)
        )""")
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS tenant_audit_log (
            id serial PRIMARY KEY,
            tenant_id integer NOT NULL DEFAULT {_GUC} REFERENCES tenants(id) ON DELETE CASCADE,
            user_id integer NULL,
            username varchar(100) NULL,
            action varchar(60) NOT NULL,
            target varchar(120) NULL,
            detail text NULL,
            created_at timestamp DEFAULT now()
        )""")
    # grants
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON login_attempts, idempotency_keys, tenant_audit_log TO {APP_ROLE}")
    for _seq in ("login_attempts_id_seq", "idempotency_keys_id_seq", "tenant_audit_log_id_seq"):
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {_seq} TO {APP_ROLE}")
    # RLS on the tenant-scoped tables (idempotent)
    for tbl in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"CREATE POLICY tenant_isolation ON {tbl} USING (tenant_id = {_GUC}) WITH CHECK (tenant_id = {_GUC})")

def downgrade() -> None:
    for tbl in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
    op.execute("DROP TABLE IF EXISTS tenant_audit_log")
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
    op.execute("DROP TABLE IF EXISTS login_attempts")
