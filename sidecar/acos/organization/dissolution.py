"""公司解散协调器 + 5 个消费者（session 消费者在 runtime/employee_drain_port.py）。

6 个消费者：
  organization, task, session, knowledge, provider, backend

全部 watermark completed 后才允许 complete_dissolution。
"""

from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from acos.organization.service import OrganizationService
from acos.rpc.errors import create_error, ORG_STATE_INVALID


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 5 个消费者 ────────────────────────────────────────────────────────────


async def dissolution_organization_consumer(db_path: str, company_id: str) -> None:
    """解散 Organization 消费者：清空 leader → 重派 employee_type → 归档部门/职员。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE departments SET leader_employee_id = NULL, version = version + 1 WHERE company_id = ?",
            (company_id,),
        )
        await db.execute(
            "UPDATE employees SET employee_type = 'employee', version = version + 1 "
            "WHERE company_id = ? AND deleted_at IS NULL",
            (company_id,),
        )
        await db.execute(
            "UPDATE departments SET status = 'archived', version = version + 1 "
            "WHERE company_id = ? AND status != 'archived'",
            (company_id,),
        )
        await db.execute(
            "UPDATE employees SET status = 'archived', version = version + 1 "
            "WHERE company_id = ? AND status != 'archived'",
            (company_id,),
        )
        await db.commit()


async def dissolution_task_consumer(db_path: str, company_id: str) -> None:
    """解散 Task 消费者：取消/终止运行中任务。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE task_nodes
               SET status = 'cancelled', version = version + 1, updated_at = ?
               WHERE company_id = ? AND status NOT IN ('succeeded', 'failed', 'dead_letter', 'cancelled')""",
            (_now_iso(), company_id),
        )
        await db.commit()


async def dissolution_knowledge_consumer(db_path: str, company_id: str) -> None:
    """解散 Knowledge 消费者：置只读，停止 ingestion/reindex。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE knowledge_policies
               SET status = 'frozen', version = version + 1
               WHERE company_id = ? AND status = 'active'""",
            (company_id,),
        )
        await db.commit()


async def dissolution_provider_consumer(db_path: str, company_id: str) -> None:
    """解散 Provider 消费者：冻结新 Provider 调用。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE provider_availability
               SET available = 0, reason = 'frozen_by_dissolution'
               WHERE company_id = ?""",
            (company_id,),
        )
        await db.commit()


async def dissolution_backend_consumer(db_path: str, company_id: str) -> None:
    """解散 Backend 消费者：排空并禁用 Backend。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """UPDATE backend_leases SET status = 'released', updated_at = ?
               WHERE company_id = ? AND status = 'active'""",
            (_now_iso(), company_id),
        )
        await db.execute(
            """UPDATE backends SET status = 'disabled', version = version + 1
               WHERE company_id = ? AND status != 'disabled'""",
            (company_id,),
        )
        await db.commit()


# ── 消费者注册表 ──────────────────────────────────────────────────────────

DISSOLUTION_CONSUMERS: dict[str, object] = {
    "organization": dissolution_organization_consumer,
    "task": dissolution_task_consumer,
    "knowledge": dissolution_knowledge_consumer,
    "provider": dissolution_provider_consumer,
    "backend": dissolution_backend_consumer,
    # session 消费者在 EmployeeDrainRuntimePort.on_company_dissolution_started
}


# ── 协调器 ────────────────────────────────────────────────────────────────


class DissolutionOrchestrator:
    """协调 6 个消费者完成公司解散。"""

    CONSUMERS = ["organization", "task", "session", "knowledge", "provider", "backend"]

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _ensure_watermarks_table(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS dissolution_watermarks (
                    company_id TEXT NOT NULL,
                    consumer_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    completed_at TEXT,
                    error_detail TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (company_id, consumer_name)
                )"""
            )
            await db.commit()

    async def initialize_watermarks(self, company_id: str) -> None:
        """为所有 6 个消费者初始化 pending watermark（幂等）。"""
        await self._ensure_watermarks_table()
        now = _now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            for consumer in self.CONSUMERS:
                await db.execute(
                    """INSERT OR IGNORE INTO dissolution_watermarks
                       (company_id, consumer_name, status, created_at, updated_at)
                       VALUES (?, ?, 'pending', ?, ?)""",
                    (company_id, consumer, now, now),
                )
            await db.commit()

    async def check_all_consumers_completed(self, company_id: str) -> dict:
        """检查所有消费者 watermark 是否完成。返回 {completed: bool, pending: [...]}"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT consumer_name, status FROM dissolution_watermarks
                   WHERE company_id = ?""",
                (company_id,),
            )
            rows = await cursor.fetchall()

        status_map = {row["consumer_name"]: row["status"] for row in rows}
        pending = [c for c in self.CONSUMERS if status_map.get(c) != "completed"]
        return {"completed": len(pending) == 0, "pending": pending}

    async def mark_consumer_completed(
        self, company_id: str, consumer_name: str
    ) -> None:
        """幂等标记消费者完成（写 watermark）。"""
        now = _now_iso()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO dissolution_watermarks
                   (company_id, consumer_name, status, completed_at, created_at, updated_at)
                   VALUES (?, ?, 'completed', ?, ?, ?)
                   ON CONFLICT (company_id, consumer_name) DO UPDATE SET
                       status = 'completed',
                       completed_at = excluded.completed_at,
                       updated_at = excluded.updated_at,
                       version = version + 1""",
                (company_id, consumer_name, now, now, now),
            )
            await db.commit()

    async def try_complete_dissolution(self, company_id: str) -> dict:
        """尝试完成解散。全部 watermark 就绪 → 转 dissolved；否则返回 pending 列表。"""
        check = await self.check_all_consumers_completed(company_id)
        if check["completed"]:
            svc = OrganizationService(self._db_path)
            await svc.complete_dissolution(company_id)
            return {"status": "dissolved"}
        return {"status": "pending", "pending_consumers": check["pending"]}

    async def create_intervention_for_failure(
        self, company_id: str, failed_consumers: list[str], trace_id: str
    ) -> str:
        """为失败消费者创建 HumanIntervention。返回 intervention_id。"""
        from acos.interventions.repository import InterventionRepository

        repo = InterventionRepository()
        target_ref = f"company_dissolution:{company_id}"
        async with aiosqlite.connect(self._db_path) as db:
            intervention = await repo.create_or_get_open(
                db,
                company_id=company_id,
                subtype="company_dissolution",
                target_ref=target_ref,
                allowed_actions=["retry", "skip", "abort"],
                trace_id=trace_id,
            )
        return intervention.intervention_id
