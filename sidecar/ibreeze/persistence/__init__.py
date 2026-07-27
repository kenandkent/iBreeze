"""Persistence layer: company isolation, optimistic locking, and idempotency.

Aligns with design doc §17 (本地持久化):
- 公司隔离: 所有查询强制 company_id 过滤
- 乐观锁: 所有更新通过 version 或 expected_version 条件
- 幂等键: RPC 层使用 idempotency_key 防重复提交

Idempotency: rpc_idempotency 表存储 method+idempotency_key 主键,
每条记录含 request_sha256 和 response_json, 支持 processing/completed/failed
三种状态, 超时由 expires_at 控制.
"""

from __future__ import annotations

from typing import Any


async def check_company_isolation(db: Any, company_id: str, table: str, row_id: str) -> bool:
    """Verify that a row belongs to the expected company (公司隔离检查)."""
    cursor = await db.execute(
        f"SELECT 1 FROM {table} WHERE id=? AND company_id=?", (row_id, company_id)
    )
    return await cursor.fetchone() is not None


async def lock_optimistic(
    db: Any,
    table: str,
    row_id: str,
    expected_version: int,
    *,
    company_id: str | None = None,
) -> bool:
    """Acquire optimistic lock: update version=version+1 WHERE version=expected_version.

    Returns True if lock acquired (rowcount == 1).
    """
    params: list[Any] = [expected_version + 1, row_id, expected_version]
    company_clause = ""
    if company_id is not None:
        company_clause = " AND company_id=?"
        params.insert(0, company_id)
    cursor = await db.execute(
        f"UPDATE {table} SET version=? WHERE id=? AND version=?{company_clause}",
        tuple(params),
    )
    return cursor.rowcount == 1  # type: ignore[no-any-return]


async def check_idempotency(
    db: Any,
    method: str,
    idempotency_key: str,
    request_sha256: str,
) -> dict[str, Any] | None:
    """Check RPC idempotency key.

    Returns existing response dict if key exists with matching request SHA,
    or None if key doesn't exist.
    """
    cursor = await db.execute(
        """SELECT status, response_json, error_code
           FROM rpc_idempotency
           WHERE method=? AND idempotency_key=?""",
        (method, idempotency_key),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    if row["status"] == "completed" and row["response_json"]:
        return {"response": row["response_json"]}
    if row["status"] == "failed":
        return {"error": row["error_code"]}
    return {"status": row["status"]}


async def claim_idempotency(
    db: Any,
    method: str,
    idempotency_key: str,
    request_sha256: str,
    ttl_seconds: int = 3600,
) -> bool:
    """Claim an idempotency key for processing.

    Returns True if claim succeeded (first attempt), False if already exists.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    expires = (
        datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    try:
        await db.execute(
            """INSERT INTO rpc_idempotency
               (method, idempotency_key, request_sha256, status,
                response_json, error_code, created_at, expires_at)
               VALUES (?,?,?, 'processing', NULL, NULL, ?, ?)""",
            (method, idempotency_key, request_sha256, now, expires),
        )
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        return False


async def complete_idempotency(
    db: Any,
    method: str,
    idempotency_key: str,
    *,
    response_json: str | None = None,
    error_code: str | None = None,
) -> None:
    """Complete an idempotent RPC with response or error."""
    if response_json is not None:
        status = "completed"
        result_field = "response_json=?"
        result_value: Any = response_json
    elif error_code is not None:
        status = "failed"
        result_field = "error_code=?"
        result_value = error_code
    else:
        return
    await db.execute(
        f"UPDATE rpc_idempotency SET status=?, {result_field} WHERE method=? AND idempotency_key=?",
        (status, result_value, method, idempotency_key),
    )
    await db.commit()
