import time
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    sql: str
    sha256: str

    def load_sql(self) -> str:
        if self.sql.startswith("file://"):
            base = Path(__file__).resolve().parent
            file_path = base / self.sql[len("file://"):]
            return file_path.read_text("utf-8")
        return self.sql


MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        filename="001_initial.sql",
        sql="file://migrations/001_initial.sql",
        sha256="aa25f8fd64aac09755f64271ff9e4c292bc52fdbf894682a4a5c966a57913249",
    ),
]


async def ensure_migration_ledger(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            script_sha256 TEXT NOT NULL CHECK(length(script_sha256) = 64),
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
            error_message TEXT
        )
    """)


async def get_applied_migrations(db: aiosqlite.Connection) -> set[int]:
    cursor = await db.execute(
        "SELECT version, script_sha256 FROM schema_migrations WHERE status = 'completed'",
    )
    rows = await cursor.fetchall()
    return {int(row[0]) for row in rows}


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
            "INSERT OR REPLACE INTO schema_migrations (version, script_sha256, status, started_at) "
            "VALUES (?, ?, 'running', ?)",
            (str(m.version), m.sha256, started_at),
        )
        try:
            sql = m.load_sql()
            if sql and not sql.startswith("--"):
                await db.executescript(sql)
            completed_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()),
            )
            await db.execute(
                "UPDATE schema_migrations SET status = 'completed', completed_at = ? "
                "WHERE version = ?",
                (completed_at, str(m.version)),
            )
        except Exception as exc:
            error_code = str(exc)[:200]
            await db.execute(
                "UPDATE schema_migrations SET status = 'failed', error_message = ? "
                "WHERE version = ?",
                (error_code, str(m.version)),
            )
            raise
