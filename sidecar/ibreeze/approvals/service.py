"""Human approval service for external writes and uncertain recovery."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def request_external_write_approval(
    db: Any,
    company_id: str,
    *,
    run_id: str,
    target_path: str,
    action: str,
    old_hash: str | None,
    new_hash: str,
    ttl_seconds: int = 300,
) -> dict[str, object]:
    """Request approval for an external write operation."""
    approval_id = _id()
    now = _now()
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")

    await db.execute("BEGIN IMMEDIATE")
    try:
        target_json = json.dumps(
            {"path": target_path, "action": action, "old_hash": old_hash, "new_hash": new_hash},
            sort_keys=True,
        )
        await db.execute(
            """INSERT INTO human_approvals
               (id, company_id, run_id, approval_type,
                target_json, target_sha256, status, requested_at, expires_at)
               VALUES (?,?,'external_write',?,?, 'pending',?,?)""",
            (
                approval_id,
                company_id,
                run_id,
                target_json,
                new_hash,
                now,
                expires_at,
            ),
        )

        await db.commit()
        return {
            "id": approval_id,
            "approval_type": "external_write",
            "status": "pending",
            "target_path": target_path,
            "action": action,
        }
    except Exception:
        await db.rollback()
        raise


async def request_uncertain_recovery_approval(
    db: Any,
    company_id: str,
    *,
    run_id: str,
    reason: str,
    ttl_seconds: int = 600,
) -> dict[str, object]:
    """Request approval for uncertain recovery operation."""
    import hashlib

    approval_id = _id()
    now = _now()
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")

    await db.execute("BEGIN IMMEDIATE")
    try:
        target_json = json.dumps({"reason": reason}, sort_keys=True)
        target_sha = hashlib.sha256(reason.encode("utf-8")).hexdigest()
        await db.execute(
            """INSERT INTO human_approvals
               (id, company_id, run_id, approval_type,
                target_json, target_sha256, status, requested_at, expires_at)
               VALUES (?,?,'uncertain_recovery',?,?, 'pending',?,?)""",
            (
                approval_id,
                company_id,
                run_id,
                target_json,
                target_sha,
                now,
                expires_at,
            ),
        )

        await db.commit()
        return {
            "id": approval_id,
            "approval_type": "uncertain_recovery",
            "status": "pending",
            "reason": reason,
        }
    except Exception:
        await db.rollback()
        raise


async def resolve_approval(
    db: Any,
    company_id: str,
    *,
    approval_id: str,
    decision: str,
) -> dict[str, object]:
    """Resolve an approval request (approve or deny)."""
    now = _now()

    await db.execute("BEGIN IMMEDIATE")
    try:
        approval = await _one(
            await db.execute(
                """SELECT * FROM human_approvals
                   WHERE id=? AND company_id=?""",
                (approval_id, company_id),
            )
        )
        if approval is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if approval["status"] != "pending":
            raise ValueError("STATE_TRANSITION_INVALID")

        new_status = "allowed" if decision in ("approve", "allowed") else "denied"

        await db.execute(
            """UPDATE human_approvals
               SET status=?, resolved_at=?
               WHERE id=? AND company_id=?""",
            (new_status, now, approval_id, company_id),
        )

        await db.commit()
        return {
            "id": approval_id,
            "status": new_status,
        }
    except Exception:
        await db.rollback()
        raise


async def list_pending_approvals(
    db: Any,
    company_id: str,
    *,
    approval_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List pending approval requests."""
    conditions = ["company_id=?", "status='pending'"]
    params: list[Any] = [company_id]

    if approval_type is not None:
        conditions.append("approval_type=?")
        params.append(approval_type)

    where = " AND ".join(conditions)
    params.append(limit)

    cursor = await db.execute(
        f"""SELECT * FROM human_approvals
            WHERE {where}
            ORDER BY requested_at ASC
            LIMIT ?""",
        tuple(params),
    )
    return [dict(row) for row in await cursor.fetchall()]


async def expire_stale_approvals(
    db: Any,
    company_id: str,
) -> int:
    """Expire approval requests that have exceeded their TTL."""
    now = _now()

    cursor = await db.execute(
        """UPDATE human_approvals
           SET status='expired', resolved_at=?
           WHERE company_id=? AND status='pending'
           AND expires_at < ?""",
        (now, company_id, now),
    )
    await db.commit()
    return cursor.rowcount
