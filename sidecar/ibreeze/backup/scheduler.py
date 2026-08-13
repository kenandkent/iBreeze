"""Backup scheduling."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def should_run_daily_backup(db: Any) -> bool:
    """Check if a daily backup should run (>24h since last)."""
    cursor = await db.execute("SELECT created_at FROM backup_records WHERE backup_type = 'daily' ORDER BY created_at DESC LIMIT 1")
    last = await cursor.fetchone()
    if not last:
        return True

    last_time = datetime.fromisoformat(dict(last)["created_at"].replace("Z", "+00:00"))
    now = datetime.now(UTC)
    hours_since = (now - last_time).total_seconds() / 3600
    return hours_since >= 24


async def should_run_pre_upgrade_backup(db: Any) -> bool:
    """Check if a pre-upgrade backup should run (always True)."""
    return True


async def trigger_daily_backup(db: Any, base_path: str) -> dict[str, Any] | None:
    """Trigger a daily backup if needed."""
    if not await should_run_daily_backup(db):
        return None

    from .packager import create_backup_package
    from .records import complete_backup_record, create_backup_record

    db_path = os.path.expanduser("~/.ibreeze/profile.db")
    cas_path = os.path.expanduser("~/.ibreeze/artifacts")
    output_dir = os.path.join(base_path, "backups")
    os.makedirs(output_dir, exist_ok=True)

    result = create_backup_package(db_path, cas_path, output_dir, backup_type="daily")

    record = await create_backup_record(
        db,
        backup_type="daily",
        file_path=result["archive_path"],
        sha256=result["archive_sha256"],
        file_size=result["archive_size"],
        manifest=result["manifest"],
    )

    await complete_backup_record(db, record["id"])

    return {
        "backup_id": record["id"],
        "archive_path": result["archive_path"],
        "created_at": result["created_at"],
    }


async def apply_retention_policy(db: Any) -> dict[str, Any]:
    """Apply 7-day + 4-week retention policy.

    Daily backups older than 7 days and weekly backups older than
    4 weeks are marked deleted. Manual and pre_upgrade backups
    are never auto-deleted.
    """
    now = datetime.now(UTC)
    deleted = 0

    cursor = await db.execute(
        "SELECT id, backup_type, created_at FROM backup_records "
        "WHERE backup_type != 'manual' "
        "AND status = 'completed' "
        "ORDER BY created_at DESC"
    )
    backups = await cursor.fetchall()

    if not backups:
        return {"deleted": 0}

    daily_cutoff = now - timedelta(days=7)
    weekly_cutoff = now - timedelta(weeks=4)

    for backup in backups:
        backup_dict = dict(backup)
        backup_time = datetime.fromisoformat(backup_dict["created_at"].replace("Z", "+00:00"))

        should_delete = False
        if backup_dict["backup_type"] == "daily" and backup_time < daily_cutoff:
            should_delete = True
        elif backup_dict["backup_type"] == "weekly" and backup_time < weekly_cutoff:
            should_delete = True

        if should_delete:
            await db.execute(
                "UPDATE backup_records SET status = 'deleted' WHERE id = ?",
                (backup_dict["id"],),
            )
            deleted += 1

    return {"deleted": deleted}
