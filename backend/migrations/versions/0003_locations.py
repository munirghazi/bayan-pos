"""Phase 1: locations + registers, user.location_id, sale.register_id

Revision ID: 0003_locations
Revises: 0002_kitting
Create Date: 2026-08-03

Idempotent: the Phase-0 baseline builds tables from live models via create_all,
so on a fresh database these objects may already exist; on an existing database
they won't. Also provisions a default branch + register for every tenant.
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0003_locations"
down_revision = "0002_kitting"
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
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if not insp.has_table("locations"):
        op.create_table(
            "locations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_locations_tenant_id", "locations", ["tenant_id"])

    if not insp.has_table("registers"):
        op.create_table(
            "registers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("location_id", sa.Integer(),
                      sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_registers_tenant_id", "registers", ["tenant_id"])
        op.create_index("ix_registers_location_id", "registers", ["location_id"])

    _rls("locations")
    _rls("registers")

    if "location_id" not in [c["name"] for c in insp.get_columns("users")]:
        op.add_column("users", sa.Column("location_id", sa.Integer(),
                                         sa.ForeignKey("locations.id"), nullable=True))
    if "register_id" not in [c["name"] for c in insp.get_columns("sales")]:
        op.add_column("sales", sa.Column("register_id", sa.Integer(),
                                         sa.ForeignKey("registers.id"), nullable=True))

    # Provision a default branch + register for every tenant that has none.
    tenant_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        conn.execute(sa.text("SELECT set_config('app.current_tenant', :t, false)"),
                     {"t": str(tid)})
        has_loc = conn.execute(sa.text("SELECT id FROM locations LIMIT 1")).fetchone()
        if has_loc:
            loc_id = has_loc[0]
        else:
            loc_id = conn.execute(sa.text(
                "INSERT INTO locations(tenant_id, name, is_active, created_at) "
                "VALUES (:t, 'الفرع الرئيسي', true, now()) RETURNING id"), {"t": tid}).scalar()
        has_reg = conn.execute(sa.text("SELECT 1 FROM registers LIMIT 1")).fetchone()
        if not has_reg:
            conn.execute(sa.text(
                "INSERT INTO registers(tenant_id, location_id, name, is_active, created_at) "
                "VALUES (:t, :l, 'الصندوق 1', true, now())"), {"t": tid, "l": loc_id})
    conn.execute(sa.text("SELECT set_config('app.current_tenant', '', false)"))


def downgrade() -> None:
    op.drop_column("sales", "register_id")
    op.drop_column("users", "location_id")
    for table in ("registers", "locations"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
