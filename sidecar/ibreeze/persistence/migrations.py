import time
from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    sql: str
    sha256: str


MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        filename="001_initial.sql",
        sql="-- Initial schema is handled by LocalDB._CREATE_TABLES_SQL",
        sha256="",
    ),
]


async def ensure_migration_ledger(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            version INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            error_code TEXT
        )
    """)


async def get_applied_migrations(db: aiosqlite.Connection) -> set[int]:
    cursor = await db.execute(
        "SELECT version, sha256 FROM _migrations WHERE status = 'completed'",
    )
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def run_migrations(
    db: aiosqlite.Connection,
    migrations: list[Migration] | None = None,
) -> None:
    migrations = migrations or MIGRATIONS
    await ensure_migration_ledger(db)
    applied = await get_applied_migrations(db)

    for m in migrations:
        if m.version in applied:
            continue
        now = time.time()
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        await db.execute(
            "INSERT OR REPLACE INTO _migrations (version, filename, sha256, status, started_at) "
            "VALUES (?, ?, ?, 'running', ?)",
            (m.version, m.filename, m.sha256, started_at),
        )
        try:
            if m.sql and not m.sql.startswith("--"):
                await db.executescript(m.sql)
            completed_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()),
            )
            await db.execute(
                "UPDATE _migrations SET status = 'completed', completed_at = ? "
                "WHERE version = ?",
                (completed_at, m.version),
            )
        except Exception as exc:
            error_code = str(exc)[:200]
            await db.execute(
                "UPDATE _migrations SET status = 'failed', error_code = ? "
                "WHERE version = ?",
                (error_code, m.version),
            )
            raise
