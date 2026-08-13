"""Persistence layer: company isolation, optimistic locking, and idempotency.

Aligns with design doc §17 (本地持久化):
- 公司隔离: 所有查询强制 company_id 过滤
- 乐观锁: 所有更新通过 version 或 expected_version 条件
- 幂等键: RPC 层使用 idempotency_key 防重复提交
"""

from __future__ import annotations

from typing import Any


async def check_company_isolation(db: Any, company_id: str, table: str, row_id: str) -> bool:
    """Verify that a row belongs to the expected company (公司隔离检查)."""
    cursor = await db.execute(f"SELECT 1 FROM {table} WHERE id=? AND company_id=?", (row_id, company_id))
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
    """Check RPC idempotency key. Uses the `idempotency` table (single global key)."""
    cursor = await db.execute(
        """SELECT status, response_json, error_code, request_sha256
           FROM idempotency
           WHERE idempotency_key=?""",
        (idempotency_key,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    if row["request_sha256"] != request_sha256:
        raise RuntimeError("IDEMPOTENCY_CONFLICT")
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
    expires = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(timespec="microseconds").replace("+00:00", "Z")
    from sqlite3 import IntegrityError

    try:
        await db.execute(
            """INSERT INTO idempotency
               (idempotency_key, request_sha256, status,
                response_json, error_code, created_at, expires_at)
               VALUES (?, ?, 'processing', NULL, NULL, ?, ?)""",
            (idempotency_key, request_sha256, now, expires),
        )
        return True
    except IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return False
        raise


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
        f"UPDATE idempotency SET status=?, {result_field} WHERE idempotency_key=?",
        (status, result_value, idempotency_key),
    )
