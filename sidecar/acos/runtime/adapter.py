"""Agent Runtime 接口：驱动 ProviderAdapter，把统一 RuntimeEvent 落地成 run 记录。

对照设计方案 §11.1：Runtime 不感知 provider 专有格式，只消费 ProviderAdapter 契约。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import aiosqlite

from acos.providers.base import ProviderAdapter, RuntimeEvent
from acos.rpc.errors import AcosError
from acos.runtime.models import RuntimeRun
from acos.runtime.session import RuntimeSessionStore

RT_RUN_NOT_FOUND = "RT-RUN-NOT-FOUND"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentRuntime:
    """Agent Runtime 骨架：start/send/cancel 驱动 ProviderAdapter。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._sessions = RuntimeSessionStore(db_path)

    async def start(
        self,
        adapter: ProviderAdapter,
        company_id: str,
        provider_id: str,
        model: str,
        department_id: str = "",
        employee_id: str = "",
        config: dict | None = None,
    ) -> dict:
        """创建 provider 原生会话 + runtime_session 记录。"""
        provider_session = await adapter.create_session(
            {
                "company_id": company_id,
                "provider_id": provider_id,
                "model": model,
                **(config or {}),
            }
        )
        session = await self._sessions.create(
            company_id=company_id,
            provider_id=provider_id,
            model=model,
            department_id=department_id,
            employee_id=employee_id,
            native_session_id=provider_session.native_session_id,
        )
        return {
            "session_id": session.session_id,
            "native_session_id": session.native_session_id,
            "status": session.status,
        }

    async def send(
        self,
        adapter: ProviderAdapter,
        session_id: str,
        message: str,
        task_id: str = "",
        conversation_id: str = "",
        trace_id: str = "",
        pricing_version_id: str | None = None,
    ) -> RuntimeRun:
        """执行一次 send：新建 run，消费 adapter.send() 的 RuntimeEvent 流。"""
        session = await self._sessions.get(session_id)
        run_id = f"run-{uuid.uuid4().hex}"
        trace_id = trace_id or uuid.uuid4().hex

        await self._insert_run(run_id, session_id, session.company_id, task_id,
                               conversation_id, trace_id, pricing_version_id)

        run = RuntimeRun(
            run_id=run_id,
            session_id=session_id,
            company_id=session.company_id,
            task_id=task_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            pricing_version_id=pricing_version_id,
        )

        try:
            result = adapter.send(session, message, stream=True)
            if isinstance(result, AsyncIterator):
                async for event in result:
                    self._stamp(event, run, session)
                    run.events.append(event)
            else:
                awaited = await result if hasattr(result, "__await__") else result  # type: ignore
                if isinstance(awaited, dict):
                    event = RuntimeEvent(event_type="result", payload=awaited)
                    self._stamp(event, run, session)
                    run.events.append(event)
                elif isinstance(awaited, AsyncIterator):
                    async for event in awaited:
                        self._stamp(event, run, session)
                        run.events.append(event)
        except Exception as exc:
            await self._set_status(run_id, "failed")
            run.status = "failed"
            raise AcosError("RT-RUN-FAILED", "run 执行失败", cause=str(exc)) from exc

        await self._set_status(run_id, "completed")
        run.status = "completed"
        return run

    async def cancel(self, adapter: ProviderAdapter, run_id: str) -> bool:
        """取消一个正在进行的 run。"""
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute("SELECT status FROM runtime_runs WHERE run_id = ?", (run_id,))
            row = await cur.fetchone()
        finally:
            await conn.close()
        if row is None:
            raise AcosError(RT_RUN_NOT_FOUND, "run 不存在", cause=run_id)

        ok = await adapter.cancel(run_id)
        await self._set_status(run_id, "cancelled")
        return ok

    def _stamp(self, event: RuntimeEvent, run: RuntimeRun, session) -> None:
        event.company_id = event.company_id or run.company_id
        event.department_id = event.department_id or session.department_id
        event.employee_id = event.employee_id or session.employee_id
        event.task_id = event.task_id or run.task_id
        event.conversation_id = event.conversation_id or run.conversation_id
        event.run_id = event.run_id or run.run_id
        event.trace_id = event.trace_id or run.trace_id

    async def _insert_run(self, run_id, session_id, company_id, task_id,
                          conversation_id, trace_id, pricing_version_id) -> None:
        conn = await aiosqlite.connect(self._db_path)
        try:
            now = _now_utc()
            await conn.execute(
                """INSERT INTO runtime_runs
                   (run_id, session_id, company_id, task_id, conversation_id, trace_id,
                    status, pricing_version_id, created_at, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, 1)""",
                (run_id, session_id, company_id, task_id, conversation_id, trace_id,
                 pricing_version_id, now, now),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def _set_status(self, run_id: str, status: str) -> None:
        conn = await aiosqlite.connect(self._db_path)
        try:
            await conn.execute(
                "UPDATE runtime_runs SET status = ?, updated_at = ?, version = version + 1 "
                "WHERE run_id = ?",
                (status, _now_utc(), run_id),
            )
            await conn.commit()
        finally:
            await conn.close()
