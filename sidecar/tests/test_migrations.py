from __future__ import annotations

import hashlib
from pathlib import Path

import aiosqlite
import pytest

from ibreeze.persistence.migrations import (
    MIGRATIONS,
    Migration,
    ensure_migration_ledger,
    get_applied_migrations,
    run_migrations,
)


class TestMigration:
    def test_load_sql_from_file(self) -> None:
        m = Migration(version=1, filename="001_initial.sql", sql="file://migrations/001_initial.sql", sha256="x" * 64)
        sql = m.load_sql()
        assert "CREATE TABLE" in sql

    def test_load_sql_inline(self) -> None:
        m = Migration(version=2, filename="002_test.sql", sql="SELECT 1", sha256="x" * 64)
        sql = m.load_sql()
        assert sql == "SELECT 1"

    def test_migration_001_sha256(self) -> None:
        base = Path(__file__).resolve().parent.parent / "ibreeze" / "persistence"
        file_path = base / "migrations" / "001_initial.sql"
        content = file_path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        assert actual == MIGRATIONS[0].sha256


@pytest.mark.asyncio
class TestMigrationRunner:
    async def test_ensure_migration_ledger_creates_table(self, tmp_path: Path) -> None:
        async with aiosqlite.connect(tmp_path / "test.db") as db:
            await ensure_migration_ledger(db)
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            )
            assert await cursor.fetchone() is not None

    async def test_get_applied_migrations_empty(self, tmp_path: Path) -> None:
        async with aiosqlite.connect(tmp_path / "test.db") as db:
            await ensure_migration_ledger(db)
            applied = await get_applied_migrations(db)
            assert applied == set()

    async def test_run_migrations_applies_sql(self, tmp_path: Path) -> None:
        test_migration = Migration(
            version=99,
            filename="999_test.sql",
            sql="CREATE TABLE IF NOT EXISTS test_migration_run (id INTEGER PRIMARY KEY)",
            sha256="a" * 64,
        )
        async with aiosqlite.connect(tmp_path / "test.db") as db:
            await run_migrations(db, migrations=[test_migration])
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='test_migration_run'"
            )
            assert await cursor.fetchone() is not None
            applied = await get_applied_migrations(db)
            assert 99 in applied

    async def test_run_migrations_skips_applied(self, tmp_path: Path) -> None:
        test_migration = Migration(
            version=98,
            filename="998_test.sql",
            sql="CREATE TABLE IF NOT EXISTS test_skip (id INTEGER PRIMARY KEY)",
            sha256="b" * 64,
        )
        async with aiosqlite.connect(tmp_path / "test.db") as db:
            await run_migrations(db, migrations=[test_migration])
            applied_after_first = await get_applied_migrations(db)
            assert 98 in applied_after_first
            await run_migrations(db, migrations=[test_migration])
            applied_after_second = await get_applied_migrations(db)
            assert applied_after_first == applied_after_second
