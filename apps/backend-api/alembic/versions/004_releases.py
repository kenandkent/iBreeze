"""Release-specific migrations — schema domain: releases.

Defines CatalogRelease, CatalogReleaseItem, EmergencyDisableRelease.

Revision ID: 004_releases
Revises: 003_catalog
Create Date: 2026-07-26 00:00:00.000000
"""


revision = "004_releases"
down_revision = "003_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
