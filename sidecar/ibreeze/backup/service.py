"""Backup creation, retention, and restore service."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _compute_table_stats(db_path: Path) -> dict[str, int]:
    """Compute row counts for all tables."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        stats = {}
        for table in tables:
            cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
            stats[table] = cursor.fetchone()[0]
        return stats
    finally:
        conn.close()


async def create_backup(
    db_path: Path,
    backup_dir: Path,
    *,
    backup_id: str | None = None,
) -> dict[str, Any]:
    """Create a backup with manifest."""
    bid = backup_id or _id()
    now = _now()
    backup_path = backup_dir / bid
    backup_path.mkdir(parents=True, exist_ok=True)

    db_backup_path = backup_path / "ibreeze.db"
    shutil.copy2(db_path, db_backup_path)

    table_stats = _compute_table_stats(db_backup_path)
    db_hash = _sha256_file(db_backup_path)

    manifest = {
        "backup_id": bid,
        "created_at": now,
        "database_hash": db_hash,
        "table_stats": table_stats,
        "version": 1,
    }

    manifest_path = backup_path / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, sort_keys=True, separators=(",", ":"))

    return manifest


async def restore_backup(
    backup_dir: Path,
    backup_id: str,
    target_db_path: Path,
    *,
    validate_manifest: bool = True,
) -> dict[str, Any]:
    """Restore from a backup with manifest validation."""
    backup_path = backup_dir / backup_id
    if not backup_path.exists():
        raise ValueError("BACKUP_NOT_FOUND")

    manifest_path = backup_path / "manifest.json"
    if not manifest_path.exists():
        raise ValueError("MANIFEST_NOT_FOUND")

    with open(manifest_path) as f:
        manifest = json.load(f)

    if validate_manifest:
        db_backup_path = backup_path / "ibreeze.db"
        current_hash = _sha256_file(db_backup_path)
        if current_hash != manifest.get("database_hash"):
            raise ValueError("MANIFEST_HASH_MISMATCH")

    db_backup_path = backup_path / "ibreeze.db"
    staging_path = target_db_path.with_suffix(".staging")
    shutil.copy2(db_backup_path, staging_path)

    final_path = staging_path.with_suffix("")
    staging_path.rename(final_path)

    return {
        "backup_id": backup_id,
        "restored": True,
        "target": str(final_path),
    }


async def list_backups(backup_dir: Path) -> list[dict[str, Any]]:
    """List all available backups."""
    backups = []
    if not backup_dir.exists():
        return backups

    for entry in sorted(backup_dir.iterdir()):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            backups.append(manifest)

    return backups


async def apply_retention_policy(
    backup_dir: Path,
    *,
    daily_retention: int = 7,
    weekly_retention: int = 4,
) -> dict[str, Any]:
    """Apply backup retention policy."""
    backups = await list_backups(backup_dir)
    if not backups:
        return {"deleted": 0}

    now = datetime.now(UTC)
    daily_cutoff = now - timedelta(days=daily_retention)
    weekly_cutoff = now - timedelta(weeks=weekly_retention)

    daily_backups = []
    weekly_backups = []
    to_delete = []

    for backup in backups:
        created_at = datetime.fromisoformat(backup["created_at"].replace("Z", "+00:00"))
        if created_at >= daily_cutoff:
            daily_backups.append(backup)
        elif created_at >= weekly_cutoff:
            weekly_backups.append(backup)
        else:
            to_delete.append(backup)

    deleted = 0
    for backup in to_delete:
        backup_path = backup_dir / backup["backup_id"]
        if backup_path.exists():
            shutil.rmtree(backup_path)
            deleted += 1

    return {
        "deleted": deleted,
        "daily_count": len(daily_backups),
        "weekly_count": len(weekly_backups),
    }


async def delete_backup(backup_dir: Path, backup_id: str) -> dict[str, Any]:
    """Delete a specific backup."""
    backup_path = backup_dir / backup_id
    if not backup_path.exists():
        raise ValueError("BACKUP_NOT_FOUND")

    shutil.rmtree(backup_path)
    return {"backup_id": backup_id, "deleted": True}
