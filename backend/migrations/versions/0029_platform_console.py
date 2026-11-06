"""Release 2b: platform console (admin.sahlpos.roaa.sa).

* platform_admins     — the people who run the platform. NOT tenant users: no
                        tenant_id, separate login, mandatory TOTP (2FA).
* platform_audit_log  — every platform action (and every login attempt).
                        Append-only for the app role: a trigger rejects UPDATE /
                        DELETE, and the app role is granted SELECT + INSERT only.
                        `tenant_ref` is a plain integer (no FK) so the trail of a
                        deleted tenant survives the deletion.

Neither table holds tenant data, so neither has RLS (the RLS guardrail test only
covers tables with a `tenant_id` column).

Revision ID: 0029_platform_console
Revises: 0028_entity_identity
Create Date: 2026-11-06
"""
import os

from alembic import op

revision = "0029_platform_console"
down_revision = "0028_entity_identity"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS platform_admins (
        id              serial PRIMARY KEY,
        username        varchar(50)  NOT NULL UNIQUE,
        password_hash   varchar(255) NOT NULL,
        full_name       varchar(100) NOT NULL,
        email           varchar(200),
        totp_secret     text,                       -- Fernet-encrypted base32 secret
        totp_enabled    boolean NOT NULL DEFAULT false,
        totp_last_step  bigint,                     -- replay protection
        is_active       boolean NOT NULL DEFAULT true,
        failed_count    integer NOT NULL DEFAULT 0,
        locked_until    timestamptz,
        last_login_at   timestamptz,
        last_login_ip   varchar(64),
        password_changed_at timestamptz,
        created_at      timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS platform_audit_log (
        id          bigserial PRIMARY KEY,
        admin_id    integer,
        username    varchar(50),
        action      varchar(60) NOT NULL,
        tenant_ref  integer,
        tenant_slug varchar(50),
        target      varchar(200),
        detail      jsonb,
        ip          varchar(64),
        created_at  timestamptz NOT NULL DEFAULT now()
    )""")
    # (a brand-new database gets these tables from the baseline's create_all;
    #  keep the column details identical either way)
    op.execute("ALTER TABLE platform_admins ALTER COLUMN totp_last_step TYPE bigint")
    op.execute("ALTER TABLE platform_audit_log ALTER COLUMN created_at SET NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_platform_audit_created ON platform_audit_log (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_platform_audit_tenant ON platform_audit_log (tenant_ref, created_at DESC)")

    op.execute("""
    CREATE OR REPLACE FUNCTION forbid_platform_audit_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'platform_audit_log is append-only';
    END $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS trg_platform_audit_append_only ON platform_audit_log")
    op.execute("""CREATE TRIGGER trg_platform_audit_append_only
        BEFORE UPDATE OR DELETE ON platform_audit_log
        FOR EACH ROW EXECUTE FUNCTION forbid_platform_audit_change()""")

    # Default privileges from the baseline would grant DELETE too: be explicit.
    op.execute(f"REVOKE ALL ON platform_admins, platform_audit_log FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON platform_admins TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON platform_audit_log TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE platform_admins_id_seq TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE platform_audit_log_id_seq TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_audit_log")
    op.execute("DROP FUNCTION IF EXISTS forbid_platform_audit_change()")
    op.execute("DROP TABLE IF EXISTS platform_admins")
