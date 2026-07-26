"""Create the complete central-service schema.

Revision ID: 001_initial
Revises:
Create Date: 2026-07-24 00:00:00.000000
"""

import uuid

import sqlalchemy as sa
from passlib.hash import argon2

from alembic import op
from ibreeze_backend import models as _models
from ibreeze_backend.db.session import Base

assert _models

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION protect_system_admin()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    IF OLD.protected THEN
                        RAISE EXCEPTION 'protected user cannot be deleted';
                    END IF;
                    RETURN OLD;
                END IF;
                IF OLD.protected THEN
                    IF NEW.username IS DISTINCT FROM OLD.username
                       OR NEW.user_type IS DISTINCT FROM OLD.user_type
                       OR NEW.status IS DISTINCT FROM OLD.status
                       OR NEW.protected IS DISTINCT FROM OLD.protected THEN
                        RAISE EXCEPTION 'protected user fields cannot be changed';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE TRIGGER trg_protect_system_admin
            BEFORE UPDATE OR DELETE ON users
            FOR EACH ROW EXECUTE FUNCTION protect_system_admin()
            """
        )
    )

    # ── Catalog protection triggers (defense-in-depth, aligned with 001_initial_schema.sql) ──

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION protect_catalog_resource_revision()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.status <> 'draft' THEN
                        RAISE EXCEPTION 'catalog revision must be inserted as draft'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
                    RAISE EXCEPTION 'published catalog revision is immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
                    RAISE EXCEPTION 'published catalog revision is immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF TG_OP = 'UPDATE'
                   AND NEW.status = 'published'
                   AND OLD.status <> 'validated' THEN
                    RAISE EXCEPTION 'only validated revision can be published'
                        USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in ("agents", "models", "api_providers", "skills", "compatibility_rules"):
        bind.execute(
            sa.text(
                f"""
                CREATE TRIGGER {table}_revision_guard
                BEFORE INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision()
                """
            )
        )

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION protect_catalog_version()
            RETURNS trigger AS $$
            DECLARE
                parent_status VARCHAR(16);
                parent_id UUID;
            BEGIN
                IF TG_TABLE_NAME = 'agent_versions' THEN
                    IF TG_OP = 'DELETE' THEN parent_id := OLD.agent_id; ELSE parent_id := NEW.agent_id; END IF;
                    SELECT status INTO parent_status FROM agents
                    WHERE id = parent_id FOR UPDATE;
                ELSIF TG_TABLE_NAME = 'skill_versions' THEN
                    IF TG_OP = 'DELETE' THEN parent_id := OLD.skill_id; ELSE parent_id := NEW.skill_id; END IF;
                    SELECT status INTO parent_status FROM skills
                    WHERE id = parent_id FOR UPDATE;
                END IF;
                IF parent_status = 'published' THEN
                    RAISE EXCEPTION 'published parent revision children are immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF TG_OP = 'INSERT' THEN
                    IF NEW.published_at IS NOT NULL THEN
                        RAISE EXCEPTION 'catalog version must be inserted unpublished'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END IF;
                IF OLD.published_at IS NOT NULL THEN
                    RAISE EXCEPTION 'published catalog version is immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                IF NEW.published_at IS NOT NULL AND OLD.published_at IS NULL THEN
                    RETURN NEW;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in ("agent_versions", "skill_versions"):
        bind.execute(
            sa.text(
                f"""
                CREATE TRIGGER {table}_guard
                BEFORE INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION protect_catalog_version()
                """
            )
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
            """
            CREATE TRIGGER catalog_release_items_immutable
            BEFORE INSERT OR UPDATE OR DELETE ON catalog_release_items
            FOR EACH ROW EXECUTE FUNCTION reject_catalog_release_item_mutation()
            """
        )
    )

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION reject_append_only_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'append-only row is immutable'
                    USING ERRCODE = '55000';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in ("emergency_disable_releases", "admin_audit_logs"):
        bind.execute(
            sa.text(
                f"""
                CREATE TRIGGER {table}_immutable
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
                """
            )
        )

    bind.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION protect_catalog_release()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'INSERT' THEN
                    IF NEW.status <> 'publishing' THEN
                        RAISE EXCEPTION 'catalog release must be inserted as publishing'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END IF;
                IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
                    RAISE EXCEPTION 'published catalog release is immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
                    RAISE EXCEPTION 'published catalog release is immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    bind.execute(
        sa.text(
            """
            CREATE TRIGGER catalog_releases_guard
            BEFORE INSERT OR UPDATE OR DELETE ON catalog_releases
            FOR EACH ROW EXECUTE FUNCTION protect_catalog_release()
            """
        )
    )

    existing = (
        bind.execute(
            sa.text(
                """
                SELECT user_type, protected
                FROM users
                WHERE lower(username) = 'admin'
                """
            )
        )
        .mappings()
        .first()
    )
    if existing is not None:
        if existing["user_type"] != "admin" or not existing["protected"]:
            raise RuntimeError("Existing username 'admin' is not the protected system administrator")
        return

    password_hash = argon2.using(
        type="ID",
        memory_cost=65536,
        rounds=3,
        parallelism=4,
        salt_size=16,
        digest_size=32,
    ).hash("admin123456")
    bind.execute(
        sa.text(
            """
            INSERT INTO users (
                id, user_type, username, email, password_hash, display_name,
                status, protected, must_change_password, failed_login_count,
                locked_until, last_login_at, created_at, updated_at, version
            ) VALUES (
                :id, 'admin', 'admin', NULL, :password_hash, 'admin',
                'active', TRUE, TRUE, 0,
                NULL, NULL, now(), now(), 1
            )
            """
        ),
        {"id": uuid.uuid4(), "password_hash": password_hash},
    )


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text("DROP TRIGGER IF EXISTS catalog_releases_guard ON catalog_releases"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS protect_catalog_release()"))
    for table in ("emergency_disable_releases", "admin_audit_logs"):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS reject_append_only_mutation()"))
    bind.execute(sa.text("DROP TRIGGER IF EXISTS catalog_release_items_immutable ON catalog_release_items"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS reject_catalog_release_item_mutation()"))
    for table in ("agent_versions", "skill_versions"):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {table}_guard ON {table}"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS protect_catalog_version()"))
    for table in ("agents", "models", "api_providers", "skills", "compatibility_rules"):
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {table}_revision_guard ON {table}"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS protect_catalog_resource_revision()"))
    bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_protect_system_admin ON users"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS protect_system_admin()"))
    Base.metadata.drop_all(bind=bind)
