"""Runtime session 抽象与持久化。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from acos.rpc.errors import AcosError
from acos.runtime.models import RuntimeSession

RT_SESSION_NOT_FOUND = "RT-SESSION-NOT-FOUND"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeSessionStore:
    """runtime_sessions 表读写。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(
        self,
        company_id: str,
        provider_id: str,
        model: str,
        department_id: str = "",
        employee_id: str = "",
        native_session_id: str = "",
    ) -> RuntimeSession:
        if not company_id or not provider_id or not model:
            raise AcosError("RT-VALIDATION", "创建 session 参数不完整")
        session_id = f"rs-{uuid.uuid4().hex}"
        conn = await aiosqlite.connect(self._db_path)
        try:
            now = _now_utc()
            await conn.execute(
                """INSERT INTO runtime_sessions
                   (session_id, company_id, department_id, employee_id, provider_id, model,
                    native_session_id, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, 1)""",
                (session_id, company_id, department_id, employee_id, provider_id, model,
                 native_session_id, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()
        return RuntimeSession(
            session_id=session_id,
            company_id=company_id,
            provider_id=provider_id,
            model=model,
            department_id=department_id,
            employee_id=employee_id,
            native_session_id=native_session_id,
        )

    async def get(self, session_id: str) -> RuntimeSession:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                "SELECT * FROM runtime_sessions WHERE session_id = ?", (session_id,)
            )
            row = await cur.fetchone()
        finally:
            await conn.close()
        if row is None:
            raise AcosError(RT_SESSION_NOT_FOUND, "session 不存在", cause=session_id)
        r = dict(row)
        return RuntimeSession(
            session_id=r["session_id"],
            company_id=r["company_id"],
            provider_id=r["provider_id"],
            model=r["model"],
            department_id=r["department_id"],
            employee_id=r["employee_id"],
            native_session_id=r["native_session_id"],
            status=r["status"],
            version=r["version"],
        )

    async def close(self, session_id: str) -> None:
        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                "UPDATE runtime_sessions SET status = 'closed', updated_at = ?, version = version + 1 "
                "WHERE session_id = ?",
                (_now_utc(), session_id),
            )
            await conn.commit()
        finally:
            await conn.close()
