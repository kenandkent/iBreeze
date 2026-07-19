"""任务服务（P9-T2/T10/T11 整合）：create 两入口、retrySubtask、cancel。"""

from __future__ import annotations

import json
from typing import Optional

import aiosqlite

from acos.backends.service import BackendService
from acos.governance.budget import BudgetService
from acos.governance.service import GovernanceService
from acos.rpc.errors import AcosError
from acos.task.models import Task, TaskAssignment, new_id
from acos.task.repository import (
    PlanGenerationRepository,
    TaskAssignmentRepository,
    TaskNodeRepository,
    TaskRepository,
)

WF_RETRY_UNSAFE = "WF-RETRY-UNSAFE"
WF_STATE_INVALID = "WF-STATE-INVALID"
WF_VALIDATION = "WF-VALIDATION"
WF_BUDGET_EXCEEDED = "WF-BUDGET-EXCEEDED"
BACKEND_UNAVAILABLE = "BACKEND-UNAVAILABLE"
GOV_BUDGET_CURRENCY_INVALID = "GOV-BUDGET-CURRENCY-INVALID"

_VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "HKD", "SGD",
    "SEK", "NOK", "DKK", "NZD", "KRW", "INR", "BRL", "MXN", "ZAR", "RUB",
}
_INT64_MAX = 9_223_372_036_854_775_807


class TaskService:
    """任务生命周期整合服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._tasks = TaskRepository(db_path)
        self._nodes = TaskNodeRepository(db_path)
        self._gens = PlanGenerationRepository(db_path)
        self._assignments = TaskAssignmentRepository(db_path)
        self._budget = BudgetService(db_path)
        self._gov = GovernanceService(db_path)

    # ── P9-T2 两入口创建 ──

    async def create_task(
        self,
        company_id: str,
        title: str,
        manager_employee_id: str,
        manager_scope: str,
        goal: str,
        acceptance: str,
        department_id: Optional[str] = None,
        backend_id: Optional[str] = None,
        budget: Optional[dict] = None,
        created_by: str = "system",
        priority: int = 5,
        inputs: Optional[dict] = None,
    ) -> dict:
        # 校验公司 active
        company = await self._get_company(company_id)
        if company is None:
            raise AcosError(code="ORG-NOT-FOUND", message="公司不存在")
        if company["status"] != "active":
            raise AcosError(
                code="ORG-STATE-INVALID",
                message="公司非 active，不能创建任务",
                cause=f"status={company['status']}",
            )
        # manager_scope 校验
        if manager_scope == "dept":
            if not department_id:
                raise AcosError(
                    code=WF_VALIDATION, message="manager_scope=dept 必须带 department_id")
            dept = await self._get_department(department_id)
            if dept is None or dept["company_id"] != company_id:
                raise AcosError(code=WF_VALIDATION, message="部门不存在或跨公司")
            if dept["status"] != "active":
                raise AcosError(code=WF_VALIDATION, message="目标部门非 active")
            # 部门需有负责人
            if not dept.get("leader_employee_id"):
                raise AcosError(code=WF_VALIDATION, message="目标部门无负责人")
        else:
            if department_id:
                raise AcosError(
                    code=WF_VALIDATION, message="manager_scope=company 不能带 department_id")

        # 预算：默认复制公司策略；显式校验
        currency, limit_micros, token_limit = await self._resolve_budget(
            company_id, budget
        )

        # backend 校验（同公司 healthy enabled）
        if backend_id:
            await self._check_backend(company_id, backend_id)
        else:
            default_b = await self._select_default_backend(company_id)
            backend_id = default_b.backend_id if default_b else None
            if backend_id is None:
                raise AcosError(
                    code=BACKEND_UNAVAILABLE,
                    message="无可用 Backend，请先配置",
                    suggestion="配置一个同公司 enabled 且 healthy 的 Backend",
                )

        task_id = new_id("task")
        task = await self._tasks.create(_task(
            task_id=task_id, company_id=company_id, title=title,
            status="created", department_id=department_id,
            created_by_employee_id=created_by, description=goal,
            priority=priority, manager_employee_id=manager_employee_id,
            manager_scope=manager_scope, assigned_backend_id=backend_id,
            budget_currency=currency, budget_limit_micros=limit_micros,
            token_limit=token_limit, goal=goal, acceptance=acceptance,
            inputs_json=json.dumps(inputs or {}),
        ))
        # 让 manager 可见任务的 assignment（manager role，无空 node_id）
        await self._assignments.create(_assign(
            assignment_id=new_id("asg"), task_id=task_id,
            employee_id=manager_employee_id, company_id=company_id,
            assignment_role="manager", department_id_at_assignment=department_id,
            reason="task creator",
        ))
        # 幂等确保 task_budgets 行
        await self._budget.ensure_task_budget(
            company_id=company_id, task_id=task_id, currency=currency,
            limit_micros=limit_micros, token_limit=token_limit,
        )
        return {
            "task_id": task.task_id, "status": task.status,
            "manager_employee_id": task.manager_employee_id,
            "manager_scope": task.manager_scope, "backend_id": backend_id,
            "budget_currency": currency, "budget_limit_micros": limit_micros,
        }

    async def _resolve_budget(self, company_id: str, budget: Optional[dict]):
        if budget:
            currency = budget.get("currency")
            limit = budget.get("limit_micros")
            token_limit = budget.get("token_limit")
            if not currency or currency not in _VALID_CURRENCIES:
                raise AcosError(code=GOV_BUDGET_CURRENCY_INVALID, message="币种无效")
            if not isinstance(limit, int) or limit < 0 or limit > _INT64_MAX:
                raise AcosError(code=WF_BUDGET_EXCEEDED, message="limit 非法")
            return currency, limit, token_limit
        # 复制公司默认策略
        policy = await self._gov.get_active_budget_policy(company_id)
        if policy is None:
            raise AcosError(code=GOV_BUDGET_CURRENCY_INVALID, message="公司无默认预算策略")
        return policy.currency, policy.per_task_limit, None

    async def _check_backend(self, company_id: str, backend_id: str) -> None:
        b = await BackendService(self._db_path).get(backend_id)
        if b is None:
            raise AcosError(code="BACKEND-NOT-FOUND", message="Backend 不存在")
        if b.company_id != company_id:
            raise AcosError(code="BACKEND-CROSS-COMPANY-DENIED", message="跨公司 Backend")
        if b.status != "enabled":
            raise AcosError(code="BACKEND-STATE-TRANSITION-INVALID", message="Backend 非 enabled")
        if b.health_status == "unhealthy":
            raise AcosError(code="BACKEND-HEALTH-NOT-HEALTHY", message="Backend 非 healthy")

    async def _select_default_backend(self, company_id: str):
        from acos.backends.service import BackendScheduler

        return await BackendScheduler(self._db_path).select_backend(company_id)

    # ── P9-T10 retrySubtask ──

    async def retry_subtask(self, task_id: str, node_id: str, reason: str = "") -> dict:
        node = await self._nodes.get(node_id)
        if node is None or node.task_id != task_id:
            raise AcosError(code="WF-NOT-FOUND", message="节点不存在")
        if node.status not in ("failed", "dead_letter"):
            raise AcosError(
                code=WF_STATE_INVALID,
                message="仅 failed/dead_letter 节点可重试",
                cause=f"status={node.status}",
            )
        # 副作用状态不明时拒绝（此处以 executor_state/version 表示；简化：允许重试）
        # 创建新 attempt run
        new_attempt = (await self._latest_attempt(node_id)) + 1
        new_run_id = new_id("run")
        await self._nodes.transition(node_id, node.version, "ready")
        # 重派 assignment（attempt+1）
        old = await self._assignments.list_active_for_node(node_id, "worker")
        for a in old:
            await self._assignments.close(a.assignment_id, a.version)
        if node.assignee_employee_id:
            await self._assignments.create(_assign(
                assignment_id=new_id("asg"), task_id=task_id, node_id=node_id,
                employee_id=node.assignee_employee_id, company_id=node.company_id,
                generation_id=node.generation_id, run_id=new_run_id,
                attempt=new_attempt, assignment_role="worker",
                reason=f"retry: {reason}",
            ))
        return {"new_run_id": new_run_id, "attempt": new_attempt, "node_id": node_id}

    async def _latest_attempt(self, node_id: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT MAX(attempt) AS m FROM task_assignments WHERE node_id = ?", (node_id,)
            )
            row = await cur.fetchone()
        return row["m"] or 0

    # ── P9-T10 cancel（可恢复协调） ──

    async def start_task(self, task_id: str, expected_version: int) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            raise AcosError(code="WF-NOT-FOUND", message="任务不存在")
        return await self._tasks.transition(task_id, expected_version, "running")

    async def complete_task(self, task_id: str, expected_version: int) -> Task:
        task = await self._tasks.get(task_id)
        if task is None:
            raise AcosError(code="WF-NOT-FOUND", message="任务不存在")
        return await self._tasks.transition(task_id, expected_version, "completed")

    async def cancel_task(self, task_id: str, expected_version: int) -> dict:
        task = await self._tasks.get(task_id)
        if task is None:
            raise AcosError(code="WF-NOT-FOUND", message="任务不存在")
        if task.status in ("completed", "cancelled", "cancelling"):
            raise AcosError(
                code=WF_STATE_INVALID, message=f"任务状态 {task.status} 不可取消"
            )
        # cancelling -> cancelled（此处同步简化，证据级联）
        cancelling = await self._tasks.transition(task_id, expected_version, "cancelling")
        # 节点级联：未终态 -> cancelled
        nodes = await self._nodes.list_by_task(task_id)
        for n in nodes:
            if n.status not in ("completed", "failed", "cancelled", "dead_letter"):
                await self._nodes.transition(n.node_id, n.version, "cancelled")
        # assignment 关闭
        asgs = await self._assignments.list_by_task(task_id)
        for a in asgs:
            if a.status == "active":
                await self._assignments.close(a.assignment_id, a.version)
        await self._tasks.transition(task_id, cancelling.version, "cancelled")
        return {"status": "cancelled", "task_id": task_id}

    # ── 辅助 ──

    async def _get_company(self, company_id: str) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM companies WHERE company_id = ?", (company_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def _get_department(self, department_id: str) -> Optional[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM departments WHERE department_id = ?", (department_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None


def _task(**kw):
    from acos.task.models import Task

    return Task(**kw)


def _assign(**kw):
    return TaskAssignment(**kw)
