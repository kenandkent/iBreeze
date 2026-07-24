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
    bind.execute(sa.text("DROP TRIGGER IF EXISTS trg_protect_system_admin ON users"))
    bind.execute(sa.text("DROP FUNCTION IF EXISTS protect_system_admin()"))
    Base.metadata.drop_all(bind=bind)
