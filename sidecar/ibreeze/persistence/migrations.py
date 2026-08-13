"""Compatibility migration helper used by isolated unit tests only.

Production startup uses :mod:`ibreeze.persistence.migrator` exclusively.  The
helper remains deliberately out of the application lifecycle so one profile
cannot be initialized by two ledger formats.
"""

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
            file_path = base / self.sql[len("file://") :]
            return file_path.read_text("utf-8")
        return self.sql


MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        filename="001_initial.sql",
        sql="file://migrations/001_initial.sql",
        sha256="f1a645c33219e7269b00b24ddd18502ef2683a17ce1133b4f80bccb0d22210ab",
    ),
    Migration(
        version=2,
        filename="002_review_assignment_version.sql",
        sql="file://migrations/002_review_assignment_version.sql",
        sha256="fa6db7c3355810bfdb7b62943ae0653df827f530117f3593a261975924663ed3",
    ),
    Migration(
        version=3,
        filename="003_review_report_version.sql",
        sql="file://migrations/003_review_report_version.sql",
        sha256="93ad9c15572bcfff60adf35f231190eaf523b27653e21d7218b6647bfd58eba0",
    ),
    Migration(
        version=4,
        filename="004_resolution_evidence.sql",
        sql="file://migrations/004_resolution_evidence.sql",
        sha256="7656d743d4aba23d8651cfa4ea8372c25bb87d3020dba9e1b341504d2b6813e3",
    ),
    Migration(
        version=5,
        filename="005_multi_agent_aggregation.sql",
        sql="file://migrations/005_multi_agent_aggregation.sql",
        sha256="b68033ade6d3a670725c230336a9b92fbd12b093fe220599df2a685b06b2ccfe",
    ),
    Migration(
        version=6,
        filename="006_intelligent_routing.sql",
        sql="file://migrations/006_intelligent_routing.sql",
        sha256="d21c8c09d523bb2eeb1857148f9a95b0c4c18e41e692da07839689e341e6f842",
    ),
    Migration(
        version=7,
        filename="007_routing_capability_tags.sql",
        sql="file://migrations/007_routing_capability_tags.sql",
        sha256="94104bad40fde769eb78b6b21d265847ab335c864aa78c5362090b43d33c94c1",
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
            "INSERT OR REPLACE INTO schema_migrations (version, script_sha256, status, started_at) VALUES (?, ?, 'running', ?)",
            (str(m.version), m.sha256, started_at),
        )
        try:
            sql = m.load_sql()
            if sql and not sql.startswith("--"):
                await db.executescript(sql)
            completed_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time()),
            )
            await db.execute(
                "UPDATE schema_migrations SET status = 'completed', completed_at = ? WHERE version = ?",
                (completed_at, str(m.version)),
            )
        except Exception as exc:
            error_code = str(exc)[:200]
            await db.execute(
                "UPDATE schema_migrations SET status = 'failed', error_message = ? WHERE version = ?",
                (error_code, str(m.version)),
            )
            raise
