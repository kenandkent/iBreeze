from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from ibreeze.persistence.migrator import (
    MigrationRunner,
    PreparedProfileDatabase,
    ProfileFileLock,
    prepare,
    verify_sqlite_capabilities,
)


class _AsyncIter:
    def __init__(self, items):
        self._items = list(items)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        val = self._items[self._idx]
        self._idx += 1
        return val

    def __iter__(self):
        return iter(self._items)


@pytest.mark.asyncio
class TestVerifySqliteCapabilities:
    @staticmethod
    def _make_cursor(*, fetchone_return=None, fetchall_return=None, aiter_items=None):
        cursor = AsyncMock()
        if fetchone_return is not None:
            cursor.fetchone = AsyncMock(return_value=fetchone_return)
        if fetchall_return is not None:
            cursor.fetchall = AsyncMock(return_value=fetchall_return)
        if aiter_items is not None:
            cursor.__aiter__.return_value = _AsyncIter(aiter_items)
        return cursor

    async def _make_db(self, execute_map):
        db = AsyncMock(spec=aiosqlite.Connection)

        def _side_effect(sql, parameters=()):
            for pattern, cursor in execute_map.items():
                if pattern in sql:
                    return cursor
            return AsyncMock()

        db.execute = AsyncMock(side_effect=_side_effect)
        return db

    async def test_ok(self):
        db = await self._make_db({
            "sqlite_version": self._make_cursor(fetchone_return=("3.46.0",)),
            "json_valid": self._make_cursor(fetchone_return=(1,)),
            "compile_options": self._make_cursor(aiter_items=[("ENABLE_FTS5",)]),
        })
        await verify_sqlite_capabilities(db)

    async def test_version_too_old(self):
        db = AsyncMock(spec=aiosqlite.Connection)
        cursor = self._make_cursor(fetchone_return=("3.44.0",))
        db.execute = AsyncMock(return_value=cursor)
        with pytest.raises(RuntimeError, match="SQLite version >=3.45"):
            await verify_sqlite_capabilities(db)

    async def test_exact_minimum_version(self):
        db = await self._make_db({
            "sqlite_version": self._make_cursor(fetchone_return=("3.45.0",)),
            "json_valid": self._make_cursor(fetchone_return=(1,)),
            "compile_options": self._make_cursor(aiter_items=[("ENABLE_FTS5",)]),
        })
        await verify_sqlite_capabilities(db)

    async def test_json_not_supported(self):
        db = await self._make_db({
            "sqlite_version": self._make_cursor(fetchone_return=("3.46.0",)),
            "json_valid": self._make_cursor(fetchone_return=(0,)),
        })
        with pytest.raises(AssertionError):
            await verify_sqlite_capabilities(db)

    async def test_fts5_not_available(self):
        db = await self._make_db({
            "sqlite_version": self._make_cursor(fetchone_return=("3.46.0",)),
            "json_valid": self._make_cursor(fetchone_return=(1,)),
            "compile_options": self._make_cursor(aiter_items=[("OMIT_FTS5", "ENABLE_FTS4")]),
        })
        with pytest.raises(RuntimeError, match="FTS5 not available"):
            await verify_sqlite_capabilities(db)


@pytest.mark.asyncio
class TestMigrationRunnerEnsureLedger:
    async def test_creates_schema_migrations_table(self, tmp_path):
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            await runner._ensure_ledger()
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == "schema_migrations"
        finally:
            await db.close()

    async def test_is_idempotent(self):
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            await runner._ensure_ledger()
            await runner._ensure_ledger()
        finally:
            await db.close()

    async def test_ledger_has_expected_columns(self):
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            await runner._ensure_ledger()
            cursor = await db.execute("PRAGMA table_info(schema_migrations)")
            columns = {row[1] async for row in cursor}
            assert "version" in columns
            assert "filename" in columns
            assert "script_sha256" in columns
            assert "status" in columns
            assert "started_at" in columns
            assert "completed_at" in columns
            assert "error_code" in columns
            assert "error_message" in columns
        finally:
            await db.close()


@pytest.mark.asyncio
class TestMigrationRunnerGetApplied:
    async def test_returns_empty_when_no_completed(self):
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            await runner._ensure_ledger()
            applied = await runner._get_applied()
            assert applied == set()
        finally:
            await db.close()

    async def test_returns_only_completed_versions(self):
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            await runner._ensure_ledger()
            await db.execute(
                "INSERT INTO schema_migrations (version, filename, script_sha256, status, started_at) "
                "VALUES (1, '001_ok.sql', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'completed', '2026-01-01T00:00:00Z')"
            )
            await db.execute(
                "INSERT INTO schema_migrations (version, filename, script_sha256, status, started_at) "
                "VALUES (2, '002_fail.sql', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'failed', '2026-01-01T00:00:00Z')"
            )
            await db.execute(
                "INSERT INTO schema_migrations (version, filename, script_sha256, status, started_at) "
                "VALUES (3, '003_run.sql', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'running', '2026-01-01T00:00:00Z')"
            )
            await db.commit()
            applied = await runner._get_applied()
            assert applied == {1}
        finally:
            await db.close()


@pytest.mark.asyncio
class TestMigrationRunnerApplyAll:
    async def test_applies_pending_migrations(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_create_a.sql").write_text("CREATE TABLE test_a (id INTEGER PRIMARY KEY);")
        (mig_dir / "002_create_b.sql").write_text("CREATE TABLE test_b (id INTEGER PRIMARY KEY);")

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            with patch("ibreeze.persistence.migrator.MIGRATIONS_DIR", mig_dir):
                await runner.apply_all()

            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] async for row in cursor}
            assert "test_a" in tables
            assert "test_b" in tables

            cursor = await db.execute(
                "SELECT version, status FROM schema_migrations ORDER BY version"
            )
            rows = await cursor.fetchall()
            assert len(rows) == 2
            assert rows[0]["version"] == 1
            assert rows[0]["status"] == "completed"
            assert rows[1]["version"] == 2
            assert rows[1]["status"] == "completed"
        finally:
            await db.close()

    async def test_skips_already_applied_migrations(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_foo.sql").write_text("CREATE TABLE test_foo (id INTEGER PRIMARY KEY);")

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            await db.execute(
                "CREATE TABLE schema_migrations ("
                "version INTEGER PRIMARY KEY, filename TEXT NOT NULL UNIQUE, "
                "script_sha256 TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, "
                "completed_at TEXT, error_code TEXT, error_message TEXT)"
            )
            sql = (mig_dir / "001_foo.sql").read_text("utf-8")
            sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            await db.execute(
                "INSERT INTO schema_migrations (version, filename, script_sha256, status, started_at, completed_at) "
                "VALUES (1, '001_foo.sql', ?, 'completed', '2026-01-01T00:00:00Z', '2026-01-01T00:00:01Z')",
                (sha,),
            )
            await db.commit()

            runner = MigrationRunner(db)
            with patch("ibreeze.persistence.migrator.MIGRATIONS_DIR", mig_dir):
                await runner.apply_all()

            cursor = await db.execute(
                "SELECT COUNT(*) AS cnt FROM schema_migrations WHERE status='completed'"
            )
            row = await cursor.fetchone()
            assert row["cnt"] == 1
        finally:
            await db.close()

    async def test_records_failed_on_migration_error(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_bad.sql").write_text("CREATE TABLE invalid SQL HERE;")

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            with patch("ibreeze.persistence.migrator.MIGRATIONS_DIR", mig_dir):
                with pytest.raises(Exception):
                    await runner.apply_all()

            cursor = await db.execute(
                "SELECT status, error_code FROM schema_migrations WHERE version=1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["status"] == "failed"
            assert row["error_code"] is not None
        finally:
            await db.close()

    async def test_raises_on_fk_violations(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_fk.sql").write_text(
            "CREATE TABLE parent (id INTEGER PRIMARY KEY);\n"
            "CREATE TABLE child (pid INTEGER REFERENCES parent(id));\n"
            "INSERT INTO child (pid) VALUES (999);\n"
        )

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            runner = MigrationRunner(db)
            with patch("ibreeze.persistence.migrator.MIGRATIONS_DIR", mig_dir):
                with pytest.raises(RuntimeError, match="foreign key violations"):
                    await runner.apply_all()

            cursor = await db.execute(
                "SELECT status, error_code FROM schema_migrations WHERE version=1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["status"] == "failed"
        finally:
            await db.close()

    async def test_raises_on_integrity_check_failure(self, tmp_path):
        mig_dir = tmp_path / "migrations"
        mig_dir.mkdir()
        (mig_dir / "001_corrupt.sql").write_text(
            "CREATE TABLE test_x (id INTEGER PRIMARY KEY);"
        )

        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        try:
            real_execute = db.execute

            async def _mock_execute(sql, parameters=()):
                if "integrity_check" in sql:
                    cursor = AsyncMock()
                    cursor.fetchone = AsyncMock(return_value=("not ok",))
                    return cursor
                if "foreign_key_check" in sql:
                    cursor = AsyncMock()
                    cursor.fetchall = AsyncMock(return_value=[])
                    return cursor
                return await real_execute(sql, parameters)

            async def _mock_executescript(sql):
                return None

            runner = MigrationRunner(db)
            with (
                patch("ibreeze.persistence.migrator.MIGRATIONS_DIR", mig_dir),
                patch.object(db, "execute", _mock_execute),
                patch.object(db, "executescript", _mock_executescript),
            ):
                with pytest.raises(RuntimeError, match="integrity check failed"):
                    await runner.apply_all()

            cursor = await db.execute(
                "SELECT status, error_code FROM schema_migrations WHERE version=1"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["status"] == "failed"
        finally:
            await db.close()


@pytest.mark.asyncio
class TestPrepare:
    async def test_prepare_success(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_mock = AsyncMock(spec=ProfileFileLock)
        conn_mock = AsyncMock(spec=aiosqlite.Connection)

        with (
            patch.object(ProfileFileLock, "acquire", AsyncMock(return_value=lock_mock)),
            patch("ibreeze.persistence.migrator.open_bootstrap_connection", AsyncMock(return_value=conn_mock)),
            patch("ibreeze.persistence.migrator.verify_sqlite_capabilities", AsyncMock()),
            patch.object(MigrationRunner, "apply_all", AsyncMock()),
        ):
            result = await prepare(path)

        assert isinstance(result, PreparedProfileDatabase)
        assert result.path == path
        conn_mock.close.assert_awaited_once()
        lock_mock.release.assert_not_called()

    async def test_prepare_releases_lock_on_verify_error(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_mock = AsyncMock(spec=ProfileFileLock)
        conn_mock = AsyncMock(spec=aiosqlite.Connection)

        with (
            patch.object(ProfileFileLock, "acquire", AsyncMock(return_value=lock_mock)),
            patch("ibreeze.persistence.migrator.open_bootstrap_connection", AsyncMock(return_value=conn_mock)),
            patch("ibreeze.persistence.migrator.verify_sqlite_capabilities", AsyncMock(side_effect=RuntimeError("bad sqlite"))),
        ):
            with pytest.raises(RuntimeError, match="bad sqlite"):
                await prepare(path)

        conn_mock.close.assert_awaited_once()
        lock_mock.release.assert_awaited_once()

    async def test_prepare_releases_lock_on_migration_error(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_mock = AsyncMock(spec=ProfileFileLock)
        conn_mock = AsyncMock(spec=aiosqlite.Connection)

        with (
            patch.object(ProfileFileLock, "acquire", AsyncMock(return_value=lock_mock)),
            patch("ibreeze.persistence.migrator.open_bootstrap_connection", AsyncMock(return_value=conn_mock)),
            patch("ibreeze.persistence.migrator.verify_sqlite_capabilities", AsyncMock()),
            patch.object(MigrationRunner, "apply_all", AsyncMock(side_effect=RuntimeError("migration failed"))),
        ):
            with pytest.raises(RuntimeError, match="migration failed"):
                await prepare(path)

        conn_mock.close.assert_awaited_once()
        lock_mock.release.assert_awaited_once()

    async def test_prepare_releases_lock_on_bootstrap_error(self, tmp_path):
        path = tmp_path / "profile.db"
        lock_mock = AsyncMock(spec=ProfileFileLock)

        with (
            patch.object(ProfileFileLock, "acquire", AsyncMock(return_value=lock_mock)),
            patch("ibreeze.persistence.migrator.open_bootstrap_connection", AsyncMock(side_effect=OSError("no db file"))),
        ):
            with pytest.raises(OSError, match="no db file"):
                await prepare(path)

        lock_mock.release.assert_awaited_once()

    async def test_prepare_releases_lock_on_acquire_error(self, tmp_path):
        path = tmp_path / "profile.db"

        with (
            patch.object(ProfileFileLock, "acquire", AsyncMock(side_effect=RuntimeError("cannot acquire profile lock"))),
        ):
            with pytest.raises(RuntimeError, match="cannot acquire profile lock"):
                await prepare(path)
