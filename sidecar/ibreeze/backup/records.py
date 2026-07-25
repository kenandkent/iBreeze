"""Backup records database operations."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return (
        datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


async def create_backup_record(
    db: Any,
    *,
    backup_type: str,
    file_path: str,
    sha256: str,
    file_size: int,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Create a backup record in the database."""
    record_id = _id()
    now = _now()
    await db.execute(
        "INSERT INTO backup_records "
        "(id, backup_type, archive_path, archive_size, archive_sha256, "
        "manifest_json, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'creating', ?)",
        (
            record_id,
            backup_type,
            file_path,
            file_size,
            sha256,
            json.dumps(manifest, sort_keys=True),
            now,
        ),
    )
    await db.commit()
    return {"id": record_id, "status": "creating", "created_at": now}


async def complete_backup_record(db: Any, record_id: str) -> dict[str, Any]:
    """Mark a backup record as completed."""
    now = _now()
    await db.execute(
        "UPDATE backup_records SET status = 'completed', completed_at = ? "
        "WHERE id = ?",
        (now, record_id),
    )
    await db.commit()
    return {"record_id": record_id, "status": "completed", "completed_at": now}


async def fail_backup_record(
    db: Any, record_id: str, error_code: str
) -> dict[str, Any]:
    """Mark a backup record as failed."""
    now = _now()
    await db.execute(
        "UPDATE backup_records SET status = 'failed', error_code = ?, "
        "completed_at = ? WHERE id = ?",
        (error_code, now, record_id),
    )
    await db.commit()
    return {
        "record_id": record_id,
        "status": "failed",
        "error_code": error_code,
    }


async def list_backup_records(db: Any) -> list[dict[str, Any]]:
    """List all backup records ordered by creation time."""
    cursor = await db.execute(
        "SELECT * FROM backup_records ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows] if rows else []


async def get_backup_record(db: Any, record_id: str) -> dict[str, Any] | None:
    """Get a specific backup record."""
    cursor = await db.execute(
        "SELECT * FROM backup_records WHERE id = ?",
        (record_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None
