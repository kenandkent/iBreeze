from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from ibreeze.persistence.connection import open_bootstrap_connection
from ibreeze.persistence.profile import PreparedProfileDatabase, ProfileFileLock

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def verify_sqlite_capabilities(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("SELECT sqlite_version()")
    row = await cursor.fetchone()
    assert row is not None
    version = str(row[0])
    parts = [int(x) for x in version.split(".")]
    if not (parts[0] > 3 or (parts[0] == 3 and parts[1] > 45) or (parts[0] == 3 and parts[1] == 45)):
        raise RuntimeError(f"SQLite version >=3.45 required, got {version}")
    for ext in ("json1",):
        await db.execute(f"SELECT {ext}()")
    cursor = await db.execute("PRAGMA compile_options")
    options = {row[0] async for row in cursor}
    if "ENABLE_FTS5" not in options:
        raise RuntimeError("FTS5 not available")


class MigrationRunner:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def _ensure_ledger(self) -> None:
        await self._db.execute("""
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                filename TEXT NOT NULL UNIQUE,
                script_sha256 TEXT NOT NULL CHECK(length(script_sha256)=64),
                status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
                started_at TEXT NOT NULL,
                completed_at TEXT,
                error_code TEXT,
                error_message TEXT
            )
        """)

    async def _get_applied(self) -> set[int]:
        cursor = await self._db.execute(
            "SELECT version FROM schema_migrations WHERE status = 'completed'"
        )
        return {row[0] async for row in cursor}

    async def apply_all(self) -> None:
        await self._ensure_ledger()
        applied = await self._get_applied()
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for file_path in migration_files:
            version = int(file_path.stem.split("_")[0])
            if version in applied:
                continue
            sql = file_path.read_text("utf-8")
            sha256 = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            filename = file_path.name
            started_at = _now_iso()
            await self._db.execute(
                "INSERT INTO schema_migrations (version, filename, script_sha256, status, started_at) "
                "VALUES (?, ?, ?, 'running', ?)",
                (version, filename, sha256, started_at),
            )
            try:
                await self._db.executescript(sql)

                cursor = await self._db.execute("PRAGMA foreign_key_check")
                fk_violations = await cursor.fetchall()
                if fk_violations:
                    raise RuntimeError(
                        f"Migration {version}: foreign key violations: {fk_violations}"
                    )

                cursor = await self._db.execute("PRAGMA integrity_check")
                row = await cursor.fetchone()
                if row and row[0] != "ok":
                    raise RuntimeError(
                        f"Migration {version}: integrity check failed: {row[0]}"
                    )

                completed_at = _now_iso()
                await self._db.execute(
                    "UPDATE schema_migrations SET status='completed', completed_at=? WHERE version=?",
                    (completed_at, version),
                )
                await self._db.commit()
            except Exception as exc:
                await self._db.execute(
                    "UPDATE schema_migrations SET status='failed', error_code=?, error_message=? WHERE version=?",
                    (type(exc).__name__, str(exc)[:500], version),
                )
                await self._db.commit()
                raise


async def prepare(path: Path) -> PreparedProfileDatabase:
    lock = await ProfileFileLock.acquire(path)
    try:
        bootstrap = await open_bootstrap_connection(path)
        try:
            await verify_sqlite_capabilities(bootstrap)
            runner = MigrationRunner(bootstrap)
            await runner.apply_all()
        finally:
            await bootstrap.close()
    except Exception:
        await lock.release()
        raise
    return PreparedProfileDatabase(path=path, lock=lock)
