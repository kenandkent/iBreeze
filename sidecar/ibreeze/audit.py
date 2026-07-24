"""Append-only local audit log persistence."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ibreeze.schemas import (
    AuditActorType,
    AuditLogResponse,
    AuditOutcome,
)

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "refresh_token",
        "api_key",
        "secret",
        "authorization",
        "content",
        "file_content",
    }
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sanitize(value: object, key: str = "") -> object:
    if key.lower() in _SENSITIVE_KEYS:
        if isinstance(value, str) and value:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            return {"redacted": True, "sha256": digest}
        return {"redacted": True}
    if isinstance(value, dict):
        return {
            str(child_key): _sanitize(child_value, str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


async def append_audit(
    db: Any,
    *,
    company_id: str | None,
    actor_type: AuditActorType,
    actor_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: AuditOutcome,
    detail: dict[str, object],
    trace_id: str,
) -> AuditLogResponse:
    audit_id = str(uuid.uuid4())
    now = _now()
    detail_json = json.dumps(
        _sanitize(detail),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    cursor = await db.execute(
        """INSERT INTO audit_logs
           (id,company_id,actor_type,actor_id,action,resource_type,
            resource_id,outcome,detail_json,trace_id,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            audit_id,
            company_id,
            actor_type.value,
            actor_id,
            action,
            resource_type,
            resource_id,
            outcome.value,
            detail_json,
            trace_id,
            now,
        ),
    )
    await db.commit()
    return AuditLogResponse(
        row_sequence=cursor.lastrowid,
        id=audit_id,
        company_id=company_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        detail_json=detail_json,
        trace_id=trace_id,
        created_at=datetime.fromisoformat(now.replace("Z", "+00:00")),
    )


async def list_audit(
    db: Any,
    *,
    company_id: str | None,
    after_sequence: int = 0,
    limit: int = 100,
) -> list[AuditLogResponse]:
    if company_id is None:
        cursor = await db.execute(
            """SELECT * FROM audit_logs WHERE row_sequence>?
               ORDER BY row_sequence LIMIT ?""",
            (after_sequence, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM audit_logs
               WHERE company_id=? AND row_sequence>?
               ORDER BY row_sequence LIMIT ?""",
            (company_id, after_sequence, limit),
        )
    return [
        AuditLogResponse(
            row_sequence=row["row_sequence"],
            id=row["id"],
            company_id=row["company_id"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            outcome=row["outcome"],
            detail_json=row["detail_json"],
            trace_id=row["trace_id"],
            created_at=datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ),
        )
        for row in await cursor.fetchall()
    ]
