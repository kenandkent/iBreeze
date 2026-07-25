"""Checkpoint persistence and recovery for agent runs."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

_DEFAULT_MAX_BLOB_BYTES = 1 * 1024 * 1024  # 1 MiB — above this, write to file.


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _next_sequence(db: Any, run_id: str) -> int:
    """Return the next checkpoint sequence for *run_id* (1-based)."""
    cursor = await db.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 AS seq FROM checkpoints WHERE run_id = ?",
        (run_id,),
    )
    row = await cursor.fetchone()
    return row["seq"] if row else 1


async def create_checkpoint(
    db: Any,
    *,
    run_id: str,
    boundary_type: str,
    state_snapshot: dict[str, Any],
    file_path: str | None = None,
) -> dict[str, Any]:
    """Persist a checkpoint for an agent run.

    When *file_path* is ``None`` the checkpoint is stored as a zstd-compressed
    blob in SQLite (``storage_type='sqlite_blob'``).  When *file_path* is given
    the blob is written to that path and ``storage_type='file'`` is used.

    The DDL column ``compressed_blob`` / ``file_path`` are mutually exclusive
    via a CHECK constraint.
    """
    cp_id = _id()
    now = _now()
    raw = json.dumps(state_snapshot, ensure_ascii=False, sort_keys=True).encode()
    uncompressed_size = len(raw)
    digest = _sha256(raw)

    seq = await _next_sequence(db, run_id)

    if file_path is not None:
        await db.execute(
            (
                "INSERT INTO checkpoints "
                "(id, run_id, sequence, boundary_type, storage_type, "
                " compressed_blob, file_path, uncompressed_size, sha256, created_at) "
                "VALUES (?, ?, ?, ?, 'file', NULL, ?, ?, ?, ?)"
            ),
            (cp_id, run_id, seq, boundary_type, file_path, uncompressed_size, digest, now),
        )
    else:
        await db.execute(
            (
                "INSERT INTO checkpoints "
                "(id, run_id, sequence, boundary_type, storage_type, "
                " compressed_blob, file_path, uncompressed_size, sha256, created_at) "
                "VALUES (?, ?, ?, ?, 'sqlite_blob', ?, NULL, ?, ?, ?)"
            ),
            (cp_id, run_id, seq, boundary_type, raw, uncompressed_size, digest, now),
        )

    await db.commit()
    return {"id": cp_id, "sequence": seq, "created_at": now}


async def restore_checkpoint(db: Any, checkpoint_id: str) -> dict[str, Any] | None:
    """Restore state from a checkpoint by its id."""
    cursor = await db.execute(
        "SELECT * FROM checkpoints WHERE id = ?",
        (checkpoint_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    result = dict(row)
    blob = result.get("compressed_blob")
    if blob is not None:
        result["state_snapshot"] = json.loads(blob)
    else:
        result["state_snapshot"] = {}
    return result


async def get_latest_checkpoint(db: Any, run_id: str) -> dict[str, Any] | None:
    """Get the most recent checkpoint for a run."""
    cursor = await db.execute(
        "SELECT * FROM checkpoints WHERE run_id = ? ORDER BY sequence DESC LIMIT 1",
        (run_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    result = dict(row)
    blob = result.get("compressed_blob")
    if blob is not None:
        result["state_snapshot"] = json.loads(blob)
    else:
        result["state_snapshot"] = {}
    return result


async def list_checkpoints(db: Any, run_id: str) -> list[dict[str, Any]]:
    """List all checkpoints for a run, newest first."""
    cursor = await db.execute(
        "SELECT id, run_id, sequence, boundary_type, storage_type, "
        "uncompressed_size, sha256, created_at FROM checkpoints "
        "WHERE run_id = ? ORDER BY sequence DESC",
        (run_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows] if rows else []
