"""Workflow 命名空间 RPC 方法（P9-T8/T11，设计命名 workflow.*）。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer
from acos.task.checkpoint import CheckpointService
from acos.task.service import TaskService


class WorkflowMethods:
    """workflow.* RPC 方法集合。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._checkpoint = CheckpointService(db_path)
        self._task_svc = TaskService(db_path)

    def register_to(self, server: RPCServer) -> None:
        server.register_method("workflow.checkpoint.list", self._checkpoint_list)
        server.register_method("workflow.plan.validate", self._plan_validate)
        server.register_method("workflow.task.cancel", self._task_cancel)
        server.register_method("workflow.deadletter.resolve", self._deadletter_resolve)

    async def _checkpoint_list(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        company_id = params.get("company_id")
        if not task_id or not company_id:
            raise AcosError(code="WF-VALIDATION", message="缺少 task_id 或 company_id")
        page = params.get("page") or {}
        limit = page.get("limit", 50)
        cursor = page.get("cursor")
        return await self._checkpoint.list_for_task(
            task_id=task_id, company_id=company_id, page_limit=limit, cursor=cursor
        )

    async def _plan_validate(self, params: dict[str, Any]) -> dict[str, Any]:
        from acos.task.plan_validator import PlanValidator, ValidationContext

        task_id = params.get("task_id")
        company_id = params.get("company_id")
        dag = params.get("dag") or []
        manager_scope = params.get("manager_scope", "dept")
        department_id = params.get("department_id")
        manager_employee_id = params.get("manager_employee_id", "system")
        if not task_id or not company_id:
            raise AcosError(code="WF-VALIDATION", message="缺少 task_id/company_id")
        validator = PlanValidator(self._db_path)
        ctx = ValidationContext(
            company_id=company_id, manager_employee_id=manager_employee_id,
            manager_scope=manager_scope, department_id=department_id,
        )
        try:
            await validator.validate(dag, ctx)
        except AcosError as exc:
            rule = getattr(exc, "rule", "")
            return {"ok": False, "rule": rule, "error": exc.message}
        return {"ok": True}

    async def _task_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        expected_version = params.get("expected_version", 1)
        if not task_id:
            raise AcosError(code="WF-VALIDATION", message="缺少 task_id")
        return await self._task_svc.cancel_task(task_id, expected_version)

    async def _deadletter_resolve(self, params: dict[str, Any]) -> dict[str, Any]:
        """workflow.deadletter.resolve：人工处理 dead-letter（P9-T7/P9-T11）。

        CAS 把 dead_letter 从 open 收敛为 resolved（version CAS，并发仅一个成功），
        写 domain_events 审计。resolution 可为 'resolved' 或 'aborted'。
        """
        dead_letter_id = params.get("dead_letter_id")
        resolution = params.get("resolution", "resolved")
        expected_version = params.get("expected_version")
        if not dead_letter_id:
            raise AcosError(code="WF-VALIDATION", message="缺少 dead_letter_id")
        if resolution not in ("resolved", "aborted"):
            raise AcosError(code="WF-VALIDATION", message="resolution 必须为 resolved 或 aborted")

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM dead_letters WHERE dead_letter_id = ?", (dead_letter_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(code="WF-NOT-FOUND", message="dead_letter 不存在")
            if row["status"] != "open":
                raise AcosError(code="WF-VALIDATION", message=f"dead_letter 已是 {row['status']}，不可重复处理")
            if expected_version is not None and row["version"] != expected_version:
                raise AcosError(
                    code="SYS-OPTIMISTIC-LOCK-CONFLICT",
                    message="并发处理冲突，请重试",
                )
            cur = await db.execute(
                """UPDATE dead_letters
                   SET status = ?, version = version + 1, updated_at = datetime('now')
                   WHERE dead_letter_id = ? AND status = 'open' AND version = ?""",
                (resolution, dead_letter_id, row["version"]),
            )
            if cur.rowcount == 0:
                raise AcosError(code="SYS-OPTIMISTIC-LOCK-CONFLICT", message="并发处理冲突，请重试")
            await db.commit()

        # 联动关联 task 状态：resolved->恢复 running / aborted->终止 cancelled
        task_effect = await self._task_svc.apply_deadletter_resolution(
            row["task_id"], resolution
        )

        return {
            "dead_letter_id": dead_letter_id,
            "status": resolution,
            "task": {"task_id": row["task_id"], **task_effect},
        }
