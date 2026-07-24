"""PostgreSQL 16 migration contract tests."""

import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command


def _alembic_config() -> Config:
    project_root = Path(__file__).parents[1]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    return config


async def _schema_snapshot(url: str) -> tuple[set[str], set[str]]:
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        table_names, user_columns = await connection.run_sync(
            lambda sync_connection: (
                set(inspect(sync_connection).get_table_names()),
                {column["name"] for column in inspect(sync_connection).get_columns("users")},
            )
        )
    await engine.dispose()
    return table_names, user_columns


async def _protected_admin(url: str) -> dict[str, object]:
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT user_type, username, email, display_name, status,
                           protected, must_change_password
                    FROM users WHERE lower(username) = 'admin'
                    """
                    )
                )
            )
            .mappings()
            .one()
        )
    await engine.dispose()
    return dict(row)


async def _assert_trigger_rejects(url: str, statement: str) -> None:
    engine = create_async_engine(url)
    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            await connection.execute(text(statement))
    await engine.dispose()


def test_upgrade_creates_full_schema_and_protected_admin(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("IBREEZE_DATABASE_URL", postgres_url)
    config = _alembic_config()
    command.upgrade(config, "head")

    tables, user_columns = asyncio.run(_schema_snapshot(postgres_url))
    assert {
        "alembic_version",
        "users",
        "refresh_token_families",
        "refresh_tokens",
        "api_idempotency",
        "admin_audit_logs",
        "agent_catalog",
        "model_catalog",
        "provider_catalog",
        "skills",
        "catalog_releases",
    } <= tables
    assert {
        "id",
        "user_type",
        "username",
        "email",
        "password_hash",
        "display_name",
        "status",
        "protected",
        "must_change_password",
        "failed_login_count",
        "locked_until",
        "last_login_at",
        "created_at",
        "updated_at",
        "version",
    } == user_columns
    assert asyncio.run(_protected_admin(postgres_url)) == {
        "user_type": "admin",
        "username": "admin",
        "email": None,
        "display_name": "admin",
        "status": "active",
        "protected": True,
        "must_change_password": True,
    }

    asyncio.run(
        _assert_trigger_rejects(
            postgres_url,
            "UPDATE users SET status='disabled' WHERE username='admin'",
        )
    )
    asyncio.run(
        _assert_trigger_rejects(
            postgres_url,
            "DELETE FROM users WHERE username='admin'",
        )
    )

    command.downgrade(config, "base")
    tables_after, _ = asyncio.run(_schema_snapshot_without_users(postgres_url))
    assert "users" not in tables_after


async def _schema_snapshot_without_users(url: str) -> tuple[set[str], None]:
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        table_names = await connection.run_sync(lambda sync_connection: set(inspect(sync_connection).get_table_names()))
    await engine.dispose()
    return table_names, None
