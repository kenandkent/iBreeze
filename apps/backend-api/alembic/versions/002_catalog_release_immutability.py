"""Add manifest_json column for immutable catalog releases.

Revision ID: 002_catalog_release_immutability
Revises: 001_initial
Create Date: 2026-07-27 10:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "002_catalog_release_immutability"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_releases",
        sa.Column("manifest_json", JSONB, nullable=True),
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION reject_catalog_release_item_update()
            RETURNS trigger AS $$
            DECLARE
                parent_status VARCHAR(16);
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    SELECT status INTO parent_status
                    FROM catalog_releases
                    WHERE id = NEW.release_id
                    FOR UPDATE;
                    IF parent_status IS DISTINCT FROM 'publishing' THEN
                        RAISE EXCEPTION 'items can only be inserted into publishing release'
                            USING ERRCODE = '55000';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'UPDATE' THEN
                    SELECT status INTO parent_status
                    FROM catalog_releases
                    WHERE id = NEW.release_id
                    FOR UPDATE;
                    IF parent_status = 'published' THEN
                        RAISE EXCEPTION 'published catalog release items are immutable'
                            USING ERRCODE = '55000';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'DELETE' THEN
                    SELECT status INTO parent_status
                    FROM catalog_releases
                    WHERE id = OLD.release_id
                    FOR UPDATE;
                    IF parent_status = 'published' THEN
                        RAISE EXCEPTION 'published catalog release items are immutable'
                            USING ERRCODE = '55000';
                    END IF;
                    RETURN OLD;
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )

    bind.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS catalog_release_items_immutable ON catalog_release_items"
        )
    )
    bind.execute(
        sa.text(
            "CREATE TRIGGER catalog_release_items_immutable "
            "BEFORE INSERT OR UPDATE OR DELETE ON catalog_release_items "
            "FOR EACH ROW EXECUTE FUNCTION reject_catalog_release_item_update()"
        )
    )


def downgrade() -> None:
    op.drop_column("catalog_releases", "manifest_json")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS catalog_release_items_immutable ON catalog_release_items"
        )
    )
    bind.execute(
        sa.text("DROP FUNCTION IF EXISTS reject_catalog_release_item_update()")
    )

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION reject_catalog_release_item_mutation()
            RETURNS trigger AS $$
            DECLARE
                parent_status VARCHAR(16);
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    SELECT status INTO parent_status
                    FROM catalog_releases
                    WHERE id = NEW.release_id
                    FOR UPDATE;
                    IF parent_status IS DISTINCT FROM 'publishing' THEN
                        RAISE EXCEPTION 'items can only be inserted into publishing release'
                            USING ERRCODE = '55000';
                    END IF;
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'catalog release item is immutable'
                    USING ERRCODE = '55000';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE TRIGGER catalog_release_items_immutable "
            "BEFORE INSERT OR UPDATE OR DELETE ON catalog_release_items "
            "FOR EACH ROW EXECUTE FUNCTION reject_catalog_release_item_mutation()"
        )
    )
