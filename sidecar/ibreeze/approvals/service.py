"""Human approval service for external writes and uncertain recovery."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


_EXTERNAL_WRITE_OPERATIONS = frozenset(
    {"create_file", "replace_file", "delete_file", "create_directory"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_sha256(value: str | None, *, required: bool, field: str) -> None:
    if value is None:
        if required:
            raise ValueError(f"{field.upper()}_INVALID")
        return
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field.upper()}_INVALID")


def _validate_uuid(value: str, field: str) -> None:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field.upper()}_INVALID") from exc


def _validate_timestamp(value: str, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"{field.upper()}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field.upper()}_INVALID")


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


async def request_external_write_approval(
    db: Any,
    company_id: str,
    *,
    run_id: str,
    workspace_grant_id: str,
    target_realpath: str,
    operation: str,
    expected_old_sha256: str | None,
    source_sha256: str | None,
    ttl_seconds: int = 300,
) -> dict[str, object]:
    """Create a canonical one-shot external-write approval.

    ``expected_old_sha256`` is the Rust target *state* hash.  ``source_sha256``
    is the staged file content hash for create/replace and is null for
    delete/create-directory.  The human approval binds the same workspace
    grant and operation that the Rust reverse-RPC request must present.
    """
    if not isinstance(target_realpath, str) or not target_realpath.startswith("/"):
        raise ValueError("TARGET_PATH_INVALID")
    if operation not in _EXTERNAL_WRITE_OPERATIONS:
        raise ValueError("OPERATION_INVALID")
    _validate_sha256(expected_old_sha256, required=operation != "create_file", field="expected_old_sha256")
    _validate_sha256(source_sha256, required=operation in {"create_file", "replace_file"}, field="source_sha256")
    if operation in {"delete_file", "create_directory"} and source_sha256 is not None:
        raise ValueError("SOURCE_SHA256_INVALID")
    approval_id = _id()
    now = _now()
    expires_at = (
        (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )

    target_json = json.dumps(
        {
            "target_realpath": target_realpath,
            "operation": operation,
            "expected_old_sha256": expected_old_sha256,
            "source_sha256": source_sha256,
            "workspace_grant_id": workspace_grant_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    target_sha256 = hashlib.sha256(target_json.encode("utf-8")).hexdigest()
    await db.execute(
        """INSERT INTO human_approvals
           (id, company_id, run_id, approval_type,
            target_json, target_sha256, status, requested_at, expires_at)
           VALUES (?,?,?,'external_write',?,?, 'pending',?,?)""",
        (
            approval_id,
            company_id,
            run_id,
            target_json,
            target_sha256,
            now,
            expires_at,
        ),
    )

    return {
        "id": approval_id,
        "approval_type": "external_write",
        "status": "pending",
        "target_realpath": target_realpath,
        "operation": operation,
        "expected_old_sha256": expected_old_sha256,
        "source_sha256": source_sha256,
        "workspace_grant_id": workspace_grant_id,
    }


async def request_uncertain_recovery_approval(
    db: Any,
    company_id: str,
    *,
    run_id: str,
    tool_execution_id: str,
    input_sha256: str,
    prior_started_at: str,
    ttl_seconds: int = 600,
) -> dict[str, object]:
    """Request approval for exactly one retry of an uncertain tool call.

    The target is deliberately immutable and contains the original tool
    execution plus its input hash.  A free-form reason is not sufficient to
    prevent replaying a different side effect after approval.
    """
    _validate_uuid(run_id, "run_id")
    _validate_uuid(tool_execution_id, "tool_execution_id")
    _validate_sha256(input_sha256, required=True, field="input_sha256")
    _validate_timestamp(prior_started_at, "prior_started_at")
    approval_id = _id()
    now = _now()
    expires_at = (
        (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )

    target = {
        "run_id": run_id,
        "tool_execution_id": tool_execution_id,
        "action": "retry_once",
        "input_sha256": input_sha256,
        "prior_started_at": prior_started_at,
    }
    target_json = json.dumps(target, sort_keys=True, separators=(",", ":"))
    target_sha = hashlib.sha256(target_json.encode("utf-8")).hexdigest()
    await db.execute(
        """INSERT INTO human_approvals
           (id, company_id, run_id, approval_type,
            target_json, target_sha256, status, requested_at, expires_at)
           VALUES (?,?,?,'uncertain_recovery',?,?, 'pending',?,?)""",
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

    return {
        "id": approval_id,
        "approval_type": "uncertain_recovery",
        "status": "pending",
        **target,
    }


async def resolve_approval(
    db: Any,
    company_id: str,
    *,
    approval_id: str,
    decision: str,
) -> dict[str, object]:
    """Resolve an approval request (approve or deny)."""
    now = _now()

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

    if decision in ("approve", "approved", "allow", "allowed"):
        new_status = "allowed"
    elif decision in ("deny", "denied", "reject", "rejected"):
        new_status = "denied"
    else:
        raise ValueError("VALIDATION_FAILED")

    await db.execute(
        """UPDATE human_approvals
           SET status=?, resolved_at=?
           WHERE id=? AND company_id=?""",
        (new_status, now, approval_id, company_id),
    )

    return {
        "id": approval_id,
        "status": new_status,
    }


async def list_pending_approvals(
    db: Any,
    company_id: str,
    *,
    approval_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    """List pending approval requests."""
    conditions = [
        "company_id=?",
        "(status='pending' OR (status='allowed' AND consumed_at IS NULL))",
    ]
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
    return [
        {**dict(row), "execution_pending": row["status"] == "allowed"}
        for row in await cursor.fetchall()
    ]


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
    return cursor.rowcount  # type: ignore[no-any-return]
