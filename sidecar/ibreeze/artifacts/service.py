"""Artifact CAS (Content-Addressable Storage) service."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def create_artifact(
    db: Any,
    company_id: str,
    *,
    company_task_id: str,
    artifact_type: str,
    content: bytes,
    filename: str,
    mime_type: str,
    created_by_employee_id: str,
    supersedes_artifact_id: str | None = None,
) -> dict[str, object]:
    """Create an immutable artifact with CAS storage."""
    content_hash = _sha256(content)
    artifact_id = _id()
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        existing = await _one(
            await db.execute(
                "SELECT id FROM artifacts WHERE company_id=? AND object_sha256=?",
                (company_id, content_hash),
            )
        )
        if existing is not None:
            return {
                "id": existing["id"],
                "content_sha256": content_hash,
                "deduplicated": True,
            }

        await db.execute(
            """INSERT INTO artifacts
               (id, company_id, company_task_id, artifact_type,
                logical_name, media_type, object_sha256, object_size,
                metadata_json, supersedes_artifact_id,
                created_by_type, created_by_run_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                artifact_id,
                company_id,
                company_task_id,
                artifact_type,
                filename,
                mime_type,
                content_hash,
                len(content),
                "{}",
                supersedes_artifact_id,
                "user",
                None,
                now,
            ),
        )

        await db.execute(
            """INSERT INTO artifact_contributors
               (artifact_id, company_id, employee_id)
               VALUES (?,?,?)""",
            (artifact_id, company_id, created_by_employee_id),
        )

        await db.commit()
        return {
            "id": artifact_id,
            "content_sha256": content_hash,
            "deduplicated": False,
        }
    except Exception:
        await db.rollback()
        raise


async def get_artifact(
    db: Any,
    company_id: str,
    artifact_id: str,
) -> dict[str, object] | None:
    """Retrieve artifact metadata."""
    return await _one(
        await db.execute(
            "SELECT * FROM artifacts WHERE id=? AND company_id=?",
            (artifact_id, company_id),
        )
    )


async def list_artifacts(
    db: Any,
    company_id: str,
    *,
    company_task_id: str | None = None,
    artifact_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List artifacts with optional filters."""
    conditions = ["company_id=?"]
    params: list[Any] = [company_id]

    if company_task_id is not None:
        conditions.append("company_task_id=?")
        params.append(company_task_id)
    if artifact_type is not None:
        conditions.append("artifact_type=?")
        params.append(artifact_type)

    where = " AND ".join(conditions)
    params.append(limit)

    cursor = await db.execute(
        f"""SELECT * FROM artifacts
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?""",
        tuple(params),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def get_artifact_version_chain(
    db: Any,
    company_id: str,
    artifact_id: str,
) -> list[dict[str, object]]:
    """Get the version chain for an artifact (supersedes chain)."""
    chain = []
    current_id = artifact_id

    while current_id is not None:
        artifact = await get_artifact(db, company_id, current_id)
        if artifact is None:
            break
        chain.append(artifact)
        current_id = artifact.get("supersedes_artifact_id")

    return chain


async def get_artifact_content(
    db: Any,
    artifact_id: str,
    company_id: str,
) -> bytes | None:
    """Get the actual content of an artifact from CAS."""
    from .storage import get_storage

    cursor = await db.execute(
        "SELECT object_sha256 FROM artifacts WHERE id=? AND company_id=?",
        (artifact_id, company_id),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    storage = get_storage()
    return storage.read(dict(row)["object_sha256"])


async def create_artifact_with_manifest(
    db: Any,
    *,
    company_id: str,
    company_task_id: str,
    artifact_type: str,
    relative_path: str,
    content: bytes,
    created_by_employee_id: str,
    manifest: Any | None = None,
) -> dict[str, object]:
    """Create an artifact with CAS storage and manifest."""
    from .storage import get_storage

    storage = get_storage()
    result = storage.write(content)

    artifact_id = _id()
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        existing = await _one(
            await db.execute(
                "SELECT id FROM artifacts WHERE company_id=? AND object_sha256=?",
                (company_id, result["sha256"]),
            )
        )
        if existing is not None:
            await db.commit()
            return {
                "id": existing["id"],
                "content_sha256": result["sha256"],
                "deduplicated": True,
            }

        await db.execute(
            """INSERT INTO artifacts
               (id, company_id, company_task_id, artifact_type,
                logical_name, media_type, object_sha256, object_size,
                metadata_json, supersedes_artifact_id,
                created_by_type, created_by_run_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                artifact_id,
                company_id,
                company_task_id,
                artifact_type,
                relative_path,
                "application/octet-stream",
                result["sha256"],
                len(content),
                "{}",
                None,
                "user",
                None,
                now,
            ),
        )

        await db.execute(
            """INSERT INTO artifact_contributors
               (artifact_id, company_id, employee_id)
               VALUES (?,?,?)""",
            (artifact_id, company_id, created_by_employee_id),
        )

        await db.commit()
        return {
            "id": artifact_id,
            "content_sha256": result["sha256"],
            "deduplicated": False,
        }
    except Exception:
        await db.rollback()
        raise
