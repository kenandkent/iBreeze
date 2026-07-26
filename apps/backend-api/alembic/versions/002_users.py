"""User-specific migrations — schema domain: users.

Defines the User model and related identity/auth tables.

Revision ID: 002_users
Revises: 001_initial
Create Date: 2026-07-26 00:00:00.000000
"""

from alembic import op

revision = "002_users"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
