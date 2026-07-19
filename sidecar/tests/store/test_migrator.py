"""迁移执行器测试。"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from acos.store.migrator import Migrator


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.fixture
def migrations_dir(tmp_path: Path) -> str:
    d = tmp_path / "migrations"
    d.mkdir()
    return str(d)


def _write_migration(migrations_dir: str, name: str, sql: str) -> str:
    path = os.path.join(migrations_dir, f"{name}.sql")
    with open(path, "w") as f:
        f.write(sql)
    return path


async def test_ensure_migration_table(tmp_db: str) -> None:
    migrator = Migrator(tmp_db)
    await migrator.ensure_migration_table()

    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "schema_migrations"


async def test_apply_single_migration(tmp_db: str, migrations_dir: str) -> None:
    migration_path = _write_migration(
        migrations_dir,
        "0002_create_users",
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL);",
    )

    migrator = Migrator(tmp_db)
    await migrator.apply_migration(migration_path)

    applied = await migrator.get_applied_migrations()
    assert "0002_create_users" in applied

    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        row = await cursor.fetchone()
        assert row is not None


async def test_migration_idempotent(tmp_db: str, migrations_dir: str) -> None:
    migration_path = _write_migration(
        migrations_dir,
        "0003_create_items",
        "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, title TEXT);",
    )

    migrator = Migrator(tmp_db)
    await migrator.apply_migration(migration_path)
    await migrator.apply_migration(migration_path)

    applied = await migrator.get_applied_migrations()
    count = sum(1 for v in applied if v == "0003_create_items")
    assert count == 1


async def test_get_applied_migrations(tmp_db: str, migrations_dir: str) -> None:
    _write_migration(
        migrations_dir,
        "0004_alpha",
        "CREATE TABLE IF NOT EXISTS alpha (id INTEGER PRIMARY KEY);",
    )
    _write_migration(
        migrations_dir,
        "0005_beta",
        "CREATE TABLE IF NOT EXISTS beta (id INTEGER PRIMARY KEY);",
    )

    migrator = Migrator(tmp_db)
    await migrator.run_pending_migrations(migrations_dir)

    applied = await migrator.get_applied_migrations()
    assert applied == ["0004_alpha", "0005_beta"]


async def test_run_pending_migrations(tmp_db: str, migrations_dir: str) -> None:
    _write_migration(
        migrations_dir,
        "0006_create_orders",
        "CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, total REAL);",
    )
    _write_migration(
        migrations_dir,
        "0007_add_status",
        "ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'pending';",
    )

    migrator = Migrator(tmp_db)
    await migrator.run_pending_migrations(migrations_dir)

    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute("PRAGMA table_info(orders)")
        columns = {row[1] for row in await cursor.fetchall()}
        assert "status" in columns
        assert "total" in columns

    applied = await migrator.get_applied_migrations()
    assert len(applied) == 2
