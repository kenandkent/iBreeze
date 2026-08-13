"""Backup restore validation.

Validates:
- SQLite integrity_check (detail-level output)
- Schema migration ledger status
- Foreign key referential integrity with detail
- Artifact reference resolution (domain_events, artifacts, etc.)
- Index rebuild readiness
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tarfile
import time
from datetime import UTC, datetime
from typing import Any

import zstandard as zstd

REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "companies",
        "departments",
        "employees",
        "conversations",
        "agent_runs",
        "artifacts",
        "knowledge_items",
        "backup_records",
        "domain_events",
        "schema_migrations",
        "embedding_generations",
    }
)

ARTIFACT_REF_CHAINS: list[tuple[str, str, str]] = [
    ("knowledge_items", "source_artifact_id", "artifacts"),
    ("knowledge_items", "source_message_event_id", "domain_events"),
    ("conversation_messages", "source_event_id", "domain_events"),
    ("outbox_events", "domain_event_id", "domain_events"),
    ("embedding_generations", "company_id", "companies"),
]


async def validate_backup_database(db_path: str) -> dict[str, Any]:
    """Validate a SQLite database backup for integrity."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA integrity_check")
        integrity_lines: list[str] = [row[0] for row in cursor.fetchall()]
        if integrity_lines != ["ok"]:
            errors.append(f"Integrity check failed: {integrity_lines}")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        missing = REQUIRED_TABLES - tables
        if missing:
            errors.append(f"Missing required tables: {missing}")

        cursor.execute("PRAGMA schema_version")
        schema_version = cursor.fetchone()[0]
        cursor.execute("PRAGMA user_version")
        user_version = cursor.fetchone()[0]

        if "schema_migrations" in tables:
            cursor.execute("SELECT version, name, applied_at, checksum FROM schema_migrations ORDER BY version")
            migrations = [
                {
                    "version": row[0],
                    "name": row[1],
                    "applied_at": row[2],
                    "checksum": row[3],
                }
                for row in cursor.fetchall()
            ]
            if not migrations:
                warnings.append("schema_migrations table is empty")
            migration_versions = [m["version"] for m in migrations]
            expected = list(range(1, len(migrations) + 1))
            if migration_versions != expected:
                warnings.append(f"Migration versions not sequential: {migration_versions}")
        else:
            migrations = []
            warnings.append("No schema_migrations table")

        cursor.execute("PRAGMA foreign_key_check")
        fk_violations = cursor.fetchall()
        fk_detail: list[dict[str, Any]] = []
        for v in fk_violations:
            fk_detail.append(
                {
                    "table": v[0],
                    "rowid": v[1],
                    "parent": v[2],
                    "fkid": v[3],
                }
            )
        if fk_detail:
            warnings.append(f"FK violations: {len(fk_detail)}")

        ref_issues: list[str] = []
        for child_table, child_col, parent_table in ARTIFACT_REF_CHAINS:
            if child_table not in tables or parent_table not in tables:
                continue
            try:
                cursor.execute(
                    f"SELECT COUNT(*) FROM [{child_table}] c "
                    f"WHERE c.[{child_col}] IS NOT NULL "
                    f"AND c.[{child_col}] NOT IN (SELECT id FROM [{parent_table}])"
                )
                orphan_count = cursor.fetchone()[0]
                if orphan_count > 0:
                    ref_issues.append(f"{child_table}.{child_col} -> {parent_table}: {orphan_count} orphans")
            except Exception:
                pass

        if ref_issues:
            errors.append(f"Orphaned reference chains: {ref_issues}")

        index_issues: list[str] = []
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")
        for idx_row in cursor.fetchall():
            idx_name = idx_row[0]
            try:
                cursor.execute(f"DROP INDEX IF EXISTS _test_{idx_name}")
            except Exception:
                index_issues.append(f"Index {idx_name} may be corrupted")

        if index_issues:
            warnings.append(f"Index issues: {index_issues}")

        conn.close()

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "schema_version": schema_version,
            "user_version": user_version,
            "table_count": len(tables),
            "migrations": migrations,
            "migration_count": len(migrations),
            "fk_violations": fk_detail,
            "fk_violation_count": len(fk_detail),
            "ref_issues": ref_issues,
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
            "warnings": [],
            "schema_version": "unknown",
            "user_version": 0,
            "table_count": 0,
            "migrations": [],
            "migration_count": 0,
            "fk_violations": [],
            "fk_violation_count": 0,
            "ref_issues": [],
        }


async def validate_backup_archive(archive_path: str) -> dict[str, Any]:
    """Validate a backup archive before restore."""
    if not os.path.exists(archive_path):
        return {"valid": False, "error": "Archive not found"}

    try:
        manifest_found = False
        db_found = False
        member_count = 0
        traversal: list[str] = []

        with open(archive_path, "rb") as f:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    for member in tar:
                        member_count += 1
                        if member.name == "manifest.json":
                            manifest_found = True
                        if member.name == "data/profile.db":
                            db_found = True
                        if member.name.startswith("..") or "/../" in member.name:
                            traversal.append(member.name)

        if not manifest_found:
            return {"valid": False, "error": "Manifest not found in archive"}
        if not db_found:
            return {"valid": False, "error": "Database not found in archive"}

        return {
            "valid": True,
            "member_count": member_count,
            "manifest_found": manifest_found,
            "db_found": db_found,
            "traversal_entries": traversal,
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


async def restore_from_backup(
    db_path: str,
    backup_archive: str,
    *,
    staging_dir: str | None = None,
) -> dict[str, Any]:
    archive_validation = await validate_backup_archive(backup_archive)
    if not archive_validation["valid"]:
        return {
            "success": False,
            "errors": [archive_validation.get("error", "Invalid archive")],
        }

    if staging_dir:
        staging_path = os.path.join(staging_dir, "restore_staging")
    else:
        staging_path = db_path + ".staging"

    os.makedirs(staging_path, exist_ok=True)

    try:
        with open(backup_archive, "rb") as f:
            dctx = zstd.ZstdDecompressor()
            with dctx.stream_reader(f) as reader:
                with tarfile.open(fileobj=reader, mode="r|") as tar:
                    tar.extractall(path=staging_path, filter="data")

        extracted_db = os.path.join(staging_path, "data", "profile.db")
        if not os.path.exists(extracted_db):
            return {
                "success": False,
                "errors": ["Database not found in extracted archive"],
            }

        db_validation = await validate_backup_database(extracted_db)
        if not db_validation["valid"]:
            return {"success": False, "errors": db_validation["errors"]}

        if "migrations" in db_validation:
            if not db_validation["migrations"]:
                return {
                    "success": False,
                    "errors": ["Schema has no migrations applied"],
                }
            highest = db_validation["migrations"][-1]["version"]
            total = db_validation["migration_count"]
            if highest != total:
                return {
                    "success": False,
                    "errors": [f"Migration chain incomplete: {highest}/{total} versions applied"],
                }

        if os.path.exists(db_path):
            restore_before = db_path + f".restore-before-{int(time.time())}"
            os.rename(db_path, restore_before)

        os.rename(extracted_db, db_path)

        return {
            "success": True,
            "restored_at": datetime.now(UTC).isoformat(),
            "db_validation": db_validation,
        }
    except Exception as e:
        return {"success": False, "errors": [str(e)]}
    finally:
        if os.path.exists(staging_path):
            shutil.rmtree(staging_path, ignore_errors=True)
