"""Security hardening: end existing sessions on logout / password change / reset.

users.tokens_valid_after — a token issued before this moment is refused.
Set on logout, password change, password reset (admin or platform) and
deactivation. Tokens issued before this release carry no issue time and keep
working until they expire (at most 8 hours) unless the user logs out.

Revision ID: 0030_token_revocation
Revises: 0029_platform_console
Create Date: 2026-11-06
"""
from alembic import op

revision = "0030_token_revocation"
down_revision = "0029_platform_console"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_valid_after timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS tokens_valid_after")
