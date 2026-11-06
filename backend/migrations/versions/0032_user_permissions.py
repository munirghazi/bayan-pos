"""Per-user permissions (tester feedback).

users.permissions — JSON list of permission keys (see perms.py). NULL for admins
(they have everything). Existing non-admin users get the cashier template, which
is exactly what a cashier could do before (sell, donations, close the register).

Revision ID: 0032_user_permissions
Revises: 0031_hot_path_indexes
Create Date: 2026-11-07
"""
from alembic import op

revision = "0032_user_permissions"
down_revision = "0031_hot_path_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions jsonb")
    # users has forced RLS: the owner role running the migration must not be filtered
    forced = op.get_bind().exec_driver_sql(
        "SELECT relforcerowsecurity FROM pg_class WHERE relname='users'").scalar()
    if forced:
        op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
    op.execute("""UPDATE users SET permissions = '["sell","donate","register_close"]'::jsonb
                  WHERE role <> 'admin' AND permissions IS NULL""")
    op.execute("UPDATE users SET role = 'cashier' WHERE role NOT IN ('admin','cashier','supervisor','storekeeper','custom')")
    if forced:
        op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS permissions")
