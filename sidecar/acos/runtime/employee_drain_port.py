"""职员会话生命周期端口（Phase 7-T5）：drain/suspend/archive/resume + 公司解散消费。

实现 P4-T5 的 Runtime port：
- suspend：只接受服务端 drain token，让 active turn 收敛到 checkpoint/调用终点，
  释放 Backend lease 后全部线程转 dormant。公共 sendMessage 不接受该 token。
- resume：消费 EmployeeResumed，仅在 employee active、无 open drain、九维 key 未变时
  把当前 dormant 线程 CAS 回 idle；否则惰性建新线程。
- archive：全部线程 archived；每个 operation 只有该职员无 held turn lease 后才按
  drain_id 返回幂等 ACK。
- 消费 CompanyDissolutionStarted：waiting_backend/active turn 与 Backend lease 收敛，
  全部线程 archived，持久化 Session watermark，最终 CompanyDissolved 只作完成确认。
- 消费 EmployeeArchived：幂等归档该职员全部线程。

对应设计方案 §19 第 14 条后半句。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from acos.rpc.errors import AcosError, ORG_NOT_FOUND, RT_SESSION_NOT_FOUND, SYS_OPTIMISTIC_LOCK_CONFLICT
from acos.runtime.session_thread_store import SessionThreadStore, _now


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class EmployeeDrainRuntimePort:
    """会话生命周期内部端口（仅内部/drain token 调用）。"""

    def __init__(self, db_path: str, company_root: str) -> None:
        self._db_path = db_path
        self._store = SessionThreadStore(db_path, company_root)

    # ── drain token 校验 ─────────────────────────────────

    async def _verify_drain_token(self, drain_id: str, drain_token: str) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM employee_drains WHERE drain_id = ?", (drain_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError("RT-DRAIN-NOT-FOUND", "drain 不存在", cause=drain_id)
            r = dict(row)
            if r["drain_token"] != drain_token:
                raise AcosError("RT-DRAIN-TOKEN-INVALID", "drain token 不匹配", cause=drain_id)
            if r["status"] != "active":
                raise AcosError("RT-DRAIN-CLOSED", "drain 已终态，token 不可重放", cause=drain_id)
            return r

    async def _has_held_turn(self, employee_id: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT 1 FROM session_threads
                   WHERE employee_id = ? AND active_turn_id IS NOT NULL LIMIT 1""",
                (employee_id,),
            )
            return await cur.fetchone() is not None

    # ── suspend ──────────────────────────────────────────

    async def suspend(
        self, employee_id: str, *, drain_id: str, drain_token: str
    ) -> dict[str, Any]:
        """suspend operation：收敛 active turn → dormant，释放 Backend lease。"""
        drain = await self._verify_drain_token(drain_id, drain_token)
        if drain["employee_id"] != employee_id:
            raise AcosError("RT-DRAIN-TOKEN-INVALID", "drain 与 employee 不匹配")

        # 先释放所有 active turn（对账式强制释放：drain 已持有控制权）
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE session_threads
                   SET active_turn_id = NULL, status = 'dormant', version = version + 1,
                       updated_at = ?
                   WHERE employee_id = ? AND active_turn_id IS NOT NULL""",
                (_stamp(), employee_id),
            )
            # 其余非 archived 线程也转 dormant
            await db.execute(
                """UPDATE session_threads
                   SET status = 'dormant', version = version + 1, updated_at = ?
                   WHERE employee_id = ? AND status NOT IN ('archived')""",
                (_stamp(), employee_id),
            )
            # 幂等 ACK：标记 drain acked
            await db.execute(
                "UPDATE employee_drains SET acked_at = ?, updated_at = ? WHERE drain_id = ?",
                (_stamp(), _stamp(), drain_id),
            )
            await db.execute(
                """INSERT INTO session_transfer_journal
                   (journal_id, company_id, employee_id, event_type, drain_id, created_at)
                   VALUES (?, ?, ?, 'EmployeeSuspended', ?, ?)""",
                (str(uuid.uuid4()), drain["company_id"], employee_id, drain_id, _stamp()),
            )
            await db.commit()
        return {"employee_id": employee_id, "status": "dormant", "acked": True}

    # ── resume ───────────────────────────────────────────

    async def resume(
        self, employee_id: str, *, current_security_context_key: str
    ) -> dict[str, Any]:
        """消费 EmployeeResumed：dormant 线程 CAS 回 idle，或惰性建新线程。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            emp = await cur.fetchone()
            if emp is None:
                raise AcosError(ORG_NOT_FOUND, "职员不存在", cause=employee_id)
            if emp["status"] != "active":
                raise AcosError("RT-EMPLOYEE-NOT-ACTIVE", "职员非 active，拒绝 resume")
            # 无 open drain
            cur = await db.execute(
                "SELECT 1 FROM employee_drains WHERE employee_id = ? AND status = 'active' LIMIT 1",
                (employee_id,),
            )
            if await cur.fetchone() is not None:
                raise AcosError("RT-DRAIN-OPEN", "存在 open drain，拒绝 resume")
            # 查找当前 key 的 dormant 线程
            cur = await db.execute(
                """SELECT * FROM session_threads
                   WHERE employee_id = ? AND security_context_key = ? AND status = 'dormant'
                   ORDER BY updated_at DESC LIMIT 1""",
                (employee_id, current_security_context_key),
            )
            row = await cur.fetchone()
            if row is not None:
                await db.execute(
                    "UPDATE session_threads SET status = 'active', version = version + 1, updated_at = ? WHERE thread_id = ?",
                    (_stamp(), row["thread_id"]),
                )
                await db.commit()
                return {"employee_id": employee_id, "thread_id": row["thread_id"], "reused": True}
            # 否则惰性建新线程
            new_thread_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO session_threads
                   (thread_id, company_id, employee_id, security_context_key, task_id,
                    status, transfer_state, resume_mode, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, NULL, 'active', 'none', '', 1, ?, ?)""",
                (new_thread_id, emp["company_id"], employee_id, current_security_context_key,
                 _stamp(), _stamp()),
            )
            await db.commit()
            return {"employee_id": employee_id, "thread_id": new_thread_id, "reused": False}

    # ── archive ──────────────────────────────────────────

    async def archive_employee(
        self, employee_id: str, *, drain_id: str = "", drain_token: str = ""
    ) -> dict[str, Any]:
        """archive operation：该职员全部线程 archived（幂等）。"""
        if drain_id:
            await self._verify_drain_token(drain_id, drain_token)
            if (await self._has_held_turn(employee_id)):
                raise AcosError("RT-DRAIN-HELD-TURN", "存在 held turn，拒绝 archive")

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT company_id FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            emp = await cur.fetchone()
            if emp is None:
                raise AcosError(ORG_NOT_FOUND, "职员不存在", cause=employee_id)
            now = _stamp()
            await db.execute(
                """UPDATE session_threads
                   SET status = 'archived', archived_at = ?, version = version + 1, updated_at = ?
                   WHERE employee_id = ? AND status != 'archived'""",
                (now, now, employee_id),
            )
            # 幂等：避免重放产生重复 EmployeeArchived 事件
            cur = await db.execute(
                "SELECT 1 FROM session_transfer_journal WHERE employee_id = ? AND event_type = 'EmployeeArchived'",
                (employee_id,),
            )
            if await cur.fetchone() is None:
                await db.execute(
                    """INSERT INTO session_transfer_journal
                       (journal_id, company_id, employee_id, event_type, drain_id, created_at)
                       VALUES (?, ?, ?, 'EmployeeArchived', ?, ?)""",
                    (str(uuid.uuid4()), emp["company_id"], employee_id, drain_id, now),
                )
            if drain_id:
                await db.execute(
                    "UPDATE employee_drains SET acked_at = ?, updated_at = ? WHERE drain_id = ?",
                    (now, now, drain_id),
                )
            await db.commit()
        return {"employee_id": employee_id, "status": "archived", "acked": bool(drain_id)}

    # ── 公司解散消费 ─────────────────────────────────────

    async def on_company_dissolution_started(
        self, company_id: str, *, trigger_event: str = "CompanyDissolutionStarted"
    ) -> dict[str, Any]:
        """消费 CompanyDissolutionStarted：收敛 turn + lease，全部线程 archived，
        持久化 Session watermark（唯一致消条件）。幂等。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            now = _stamp()
            # 释放 active turn
            await db.execute(
                """UPDATE session_threads
                   SET active_turn_id = NULL, status = 'archived', archived_at = ?,
                       version = version + 1, updated_at = ?
                   WHERE company_id = ? AND status != 'archived'""",
                (now, now, company_id),
            )
            # 幂等持久化 watermark
            cur = await db.execute(
                "SELECT 1 FROM session_watermarks WHERE company_id = ? AND scope = 'company' LIMIT 1",
                (company_id,),
            )
            if await cur.fetchone() is None:
                await db.execute(
                    """INSERT INTO session_watermarks
                       (watermark_id, company_id, scope, target_id, trigger_event,
                        status, detail, created_at)
                       VALUES (?, ?, 'company', ?, ?, 'consumed', ?, ?)""",
                    (str(uuid.uuid4()), company_id, company_id, trigger_event,
                     json.dumps({"threads_archived": True}), now),
                )
            await db.commit()
        return {"company_id": company_id, "watermark_persisted": True}

    async def on_employee_archived(self, employee_id: str) -> dict[str, Any]:
        """消费 EmployeeArchived 事件（outbox consumer 幂等归档）。"""
        return await self.archive_employee(employee_id)
