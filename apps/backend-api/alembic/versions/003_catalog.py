"""Catalog-specific migrations — schema domain: catalog.

Defines Agent, Model, Provider catalog models, versioning, and bindings.

Revision ID: 003_catalog
Revises: 002_users
Create Date: 2026-07-26 00:00:00.000000
"""


revision = "003_catalog"
down_revision = ("002_users", "002_catalog_release_immutability")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
