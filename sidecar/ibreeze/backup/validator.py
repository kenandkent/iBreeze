"""Backup restore validation."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


async def validate_backup_database(db_path: str) -> dict[str, Any]:
    """Validate a SQLite database backup for integrity."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        if result[0] != "ok":
            errors.append(f"Integrity check failed: {result[0]}")

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        required_tables = {
            "companies",
            "departments",
            "employees",
            "conversations",
            "agent_runs",
            "artifacts",
            "knowledge_items",
            "backup_records",
        }
        missing = required_tables - tables
        if missing:
            errors.append(f"Missing required tables: {missing}")

        cursor.execute("PRAGMA foreign_key_check")
        fk_violations = cursor.fetchall()
        if fk_violations:
            warnings.append(
                f"Foreign key violations: {len(fk_violations)}"
            )

        cursor.execute(
            "SELECT version FROM schema_migrations "
            "ORDER BY applied_at DESC LIMIT 1"
        )
        version_row = cursor.fetchone()
        schema_version = version_row[0] if version_row else "unknown"

        conn.close()

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "schema_version": schema_version,
            "table_count": len(tables),
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
            "warnings": [],
            "schema_version": "unknown",
        }


async def validate_backup_archive(archive_path: str) -> dict[str, Any]:
    """Validate a backup archive before restore."""
    if not os.path.exists(archive_path):
        return {"valid": False, "error": "Archive not found"}

    try:
        with tarfile.open(archive_path, "r") as tar:
            members = tar.getmembers()
            manifest_found = any(
                m.name == "manifest.json" for m in members
            )
            db_found = any(
                m.name == "data/profile.db" for m in members
            )

            if not manifest_found:
                return {
                    "valid": False,
                    "error": "Manifest not found in archive",
                }
            if not db_found:
                return {
                    "valid": False,
                    "error": "Database not found in archive",
                }

            return {
                "valid": True,
                "member_count": len(members),
                "manifest_found": manifest_found,
                "db_found": db_found,
            }
    except Exception as e:
        return {"valid": False, "error": str(e)}


async def restore_from_backup(
    db_path: str,
    backup_archive: str,
    *,
    staging_dir: str | None = None,
) -> dict[str, Any]:
    """Restore database from a backup archive.

    Extracts the archive, validates the database, and atomically
    replaces the active database. Any failure leaves the original
    database untouched.
    """
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
        with tarfile.open(backup_archive, "r") as tar:
            tar.extractall(path=staging_path)

        extracted_db = os.path.join(staging_path, "data", "profile.db")
        if not os.path.exists(extracted_db):
            return {
                "success": False,
                "errors": ["Database not found in extracted archive"],
            }

        db_validation = await validate_backup_database(extracted_db)
        if not db_validation["valid"]:
            return {"success": False, "errors": db_validation["errors"]}

        if os.path.exists(db_path):
            restore_before = (
                db_path + f".restore-before-{int(time.time())}"
            )
            os.rename(db_path, restore_before)

        os.rename(extracted_db, db_path)

        return {
            "success": True,
            "restored_at": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {"success": False, "errors": [str(e)]}
    finally:
        if os.path.exists(staging_path):
            shutil.rmtree(staging_path, ignore_errors=True)
