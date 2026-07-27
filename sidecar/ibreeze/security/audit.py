"""Security audit logging — writes to the audit_logs table (H.14 DDL).

Complements the top-level ibreeze.audit module with a simplified interface
focused on security-relevant operations.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

_SENSITIVE_KEYS = frozenset({
    "password", "token", "api_key", "authorization", "cookie",
    "secret", "credential", "access_token", "refresh_token",
    "private_key", "jwt", "bearer",
})


def _sanitize(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sanitize audit detail: truncate content + redact sensitive fields."""
    if not data:
        return None
    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if key.lower() in _SENSITIVE_KEYS:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 100:
            sanitized[key] = value[:100] + f"...[truncated, sha256={hashlib.sha256(value.encode()).hexdigest()[:16]}]"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize(value)
        else:
            sanitized[key] = value
    return sanitized


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _id() -> str:
    return str(uuid.uuid4())


GENESIS_HASH = "0" * 64


def _compute_hash(row_data: str, prev_hash: str) -> str:
    """Compute SHA-256 hash for audit chain integrity."""
    combined = f"{prev_hash}|{row_data}"
    return hashlib.sha256(combined.encode()).hexdigest()


async def _get_prev_hash(db: Any, company_id: str | None) -> str:
    """Get the hash of the most recent audit log entry for the company."""
    cursor = await db.execute(
        "SELECT hash FROM audit_logs WHERE company_id = ? ORDER BY row_sequence DESC LIMIT 1",
        (company_id,),
    )
    row = await cursor.fetchone()
    return row[0] if row else GENESIS_HASH


async def log_audit(
    db: Any,
    *,
    company_id: str | None,
    actor_id: str | None,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
    trace_id: str = "",
) -> str:
    """Write an audit log entry. Returns the log ID.

    Aligns with audit_logs DDL (H.14):
      id, company_id, actor_type, actor_id, action, resource_type,
      resource_id, outcome, detail_json, trace_id, created_at,
      hash, prev_hash
    """
    # Dedup: skip if same trace_id + action + resource already logged
    if trace_id:
        existing = await db.execute(
            "SELECT id FROM audit_logs WHERE trace_id = ? AND action = ? AND resource_id = ? LIMIT 1",
            (trace_id, action, resource_id),
        )
        if await existing.fetchone():
            return ""

    log_id = _id()
    now = _now()
    sanitized = _sanitize(detail)
    detail_json = json.dumps(sanitized or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    row_data = json.dumps({
        "company_id": company_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome,
    }, sort_keys=True)
    prev_hash = await _get_prev_hash(db, company_id)
    chain_hash = _compute_hash(row_data, prev_hash)

    await db.execute(
        """INSERT INTO audit_logs
           (id, company_id, actor_type, actor_id, action, resource_type,
            resource_id, outcome, detail_json, trace_id, created_at,
            hash, prev_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            log_id, company_id, actor_type, actor_id, action, resource_type,
            resource_id, outcome, detail_json, trace_id, now,
            chain_hash, prev_hash,
        ),
    )
    await db.commit()
    return log_id


async def list_audit_logs(
    db: Any,
    *,
    company_id: str | None = None,
    actor_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    after_sequence: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List audit logs with optional filters."""
    conditions: list[str] = ["row_sequence > ?"]
    params: list[Any] = [after_sequence]

    if company_id is not None:
        conditions.append("company_id = ?")
        params.append(company_id)
    if actor_id is not None:
        conditions.append("actor_id = ?")
        params.append(actor_id)
    if action is not None:
        conditions.append("action = ?")
        params.append(action)
    if resource_type is not None:
        conditions.append("resource_type = ?")
        params.append(resource_type)

    where = " AND ".join(conditions)
    params.append(limit)

    cursor = await db.execute(
        f"SELECT * FROM audit_logs WHERE {where} ORDER BY row_sequence LIMIT ?",
        tuple(params),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows] if rows else []
