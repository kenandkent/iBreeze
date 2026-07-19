"""RPC 幂等键管理器。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite

from acos.rpc.errors import AcosError, SYS_IDEMPOTENCY_CONFLICT


class IdempotencyManager:
    """RPC 幂等键管理器。"""

    def __init__(self, retention_hours: int = 24) -> None:
        self._retention_hours = retention_hours

    def compute_request_hash(self, method: str, params: dict) -> str:
        """计算请求的确定性 hash（不含 trace_id）。"""
        canonical = json.dumps({"method": method, "params": params}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def check_and_reserve(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        actor_type: str,
        actor_id: str,
        method: str,
        idempotency_key: str,
        request_hash: str,
    ) -> dict | None:
        """检查幂等键，返回已有结果或 None（允许执行）。"""
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=self._retention_hours)).isoformat()

        row = await conn.execute_fetchall(
            "SELECT id, status, request_hash, response_ref, error_ref "
            "FROM rpc_idempotency_records "
            "WHERE company_id = ? AND actor_type = ? AND actor_id = ? "
            "AND method = ? AND idempotency_key = ?",
            (company_id, actor_type, actor_id, method, idempotency_key),
        )
        existing = row[0] if row else None

        if existing is not None:
            _id, status, stored_hash, response_ref, error_ref = existing
            if stored_hash != request_hash:
                raise AcosError(
                    code=SYS_IDEMPOTENCY_CONFLICT,
                    message="幂等键冲突：请求参数与已记录的不一致",
                    trace_id="",
                )
            if status in ("succeeded", "failed"):
                return {"status": status, "response_ref": response_ref, "error_ref": error_ref}
            # status == 'processing' — 同一执行者直接返回已有记录
            return {"status": status, "response_ref": response_ref, "error_ref": error_ref}

        # 不存在，CAS 占有
        record_id = uuid.uuid4().hex
        try:
            await conn.execute(
                "INSERT INTO rpc_idempotency_records "
                "(id, company_id, actor_type, actor_id, method, idempotency_key, "
                "request_hash, status, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', ?)",
                (record_id, company_id, actor_type, actor_id, method, idempotency_key, request_hash, expires_at),
            )
            await conn.commit()
        except Exception:
            # UNIQUE 冲突 — 有并发竞争，重新查找
            row = await conn.execute_fetchall(
                "SELECT id, status, request_hash, response_ref, error_ref "
                "FROM rpc_idempotency_records "
                "WHERE company_id = ? AND actor_type = ? AND actor_id = ? "
                "AND method = ? AND idempotency_key = ?",
                (company_id, actor_type, actor_id, method, idempotency_key),
            )
            if row:
                existing = row[0]
                _id, status, stored_hash, response_ref, error_ref = existing
                if stored_hash != request_hash:
                    raise AcosError(
                        code=SYS_IDEMPOTENCY_CONFLICT,
                        message="幂等键冲突：请求参数与已记录的不一致",
                        trace_id="",
                    )
                return {"status": status, "response_ref": response_ref, "error_ref": error_ref}
            raise

        return None

    async def complete(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        actor_type: str,
        actor_id: str,
        method: str,
        idempotency_key: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """完成幂等记录。"""
        response_ref = json.dumps(result) if result is not None else None
        error_ref = error
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE rpc_idempotency_records "
            "SET status = ?, response_ref = ?, error_ref = ?, updated_at = ? "
            "WHERE company_id = ? AND actor_type = ? AND actor_id = ? "
            "AND method = ? AND idempotency_key = ?",
            (status, response_ref, error_ref, now, company_id, actor_type, actor_id, method, idempotency_key),
        )
        await conn.commit()

    async def cleanup_expired(self, conn: aiosqlite.Connection) -> int:
        """清理过期的幂等记录。"""
        now = datetime.now(timezone.utc).isoformat()
        cursor = await conn.execute(
            "DELETE FROM rpc_idempotency_records WHERE expires_at < ?", (now,)
        )
        await conn.commit()
        return cursor.rowcount
