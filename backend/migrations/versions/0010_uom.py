"""Phase 5.3a: UoM engine (uom_categories + uoms) + product uom links

Revision ID: 0010_uom
Revises: 0009_decimal_quantities
Create Date: 2026-08-10

Idempotent; seeds default UoM (Unit/Weight/Volume) for every existing tenant.
"""
import os
import sqlalchemy as sa
from alembic import op

revision = "0010_uom"
down_revision = "0009_decimal_quantities"
branch_labels = None
depends_on = None

APP_ROLE = os.environ.get("APP_DB_ROLE", "pos_app")
_GUC = "NULLIF(current_setting('app.current_tenant', true), '')::integer"

SEED = [
    ("عدد", 0, [("حبة", 1, True), ("دستة", 12, False), ("كرتون", 24, False)]),
    ("وزن", 3, [("كجم", 1, True), ("جرام", 0.001, False), ("طن", 1000, False)]),
    ("حجم", 3, [("لتر", 1, True), ("مل", 0.001, False)]),
]


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

    if not insp.has_table("uom_categories"):
        op.create_table(
            "uom_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("decimal_places", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_uom_categories_tenant_id", "uom_categories", ["tenant_id"])

    if not insp.has_table("uoms"):
        op.create_table(
            "uoms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(),
                      sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                      nullable=False, server_default=sa.text(_GUC)),
            sa.Column("category_id", sa.Integer(),
                      sa.ForeignKey("uom_categories.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("factor", sa.Numeric(18, 6), nullable=False, server_default="1"),
            sa.Column("is_reference", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_uoms_tenant_id", "uoms", ["tenant_id"])
        op.create_index("ix_uoms_category_id", "uoms", ["category_id"])

    _rls("uom_categories")
    _rls("uoms")

    products_cols = [c["name"] for c in insp.get_columns("products")]
    for col in ("uom_id", "purchase_uom_id", "sales_uom_id"):
        if col not in products_cols:
            op.add_column("products", sa.Column(col, sa.Integer(),
                                                sa.ForeignKey("uoms.id"), nullable=True))

    # seed defaults per tenant that has none
    tenant_ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM tenants")).fetchall()]
    for tid in tenant_ids:
        conn.execute(sa.text("SELECT set_config('app.current_tenant', :t, false)"), {"t": str(tid)})
        if conn.execute(sa.text("SELECT 1 FROM uom_categories LIMIT 1")).fetchone():
            continue
        for cat_name, dp, units in SEED:
            cid = conn.execute(sa.text(
                "INSERT INTO uom_categories(tenant_id,name,decimal_places,is_active,created_at) "
                "VALUES(:t,:n,:d,true,now()) RETURNING id"), {"t": tid, "n": cat_name, "d": dp}).scalar()
            for uname, factor, is_ref in units:
                conn.execute(sa.text(
                    "INSERT INTO uoms(tenant_id,category_id,name,factor,is_reference,is_active,created_at) "
                    "VALUES(:t,:c,:n,:f,:r,true,now())"),
                    {"t": tid, "c": cid, "n": uname, "f": factor, "r": is_ref})
    conn.execute(sa.text("SELECT set_config('app.current_tenant', '', false)"))


def downgrade() -> None:
    for col in ("uom_id", "purchase_uom_id", "sales_uom_id"):
        op.drop_column("products", col)
    for table in ("uoms", "uom_categories"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
