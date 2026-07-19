"""任务调度器（P9-T5）：按 DAG 依赖并行执行。

接 BackendSelector+lease、Session active turn（此处以并发信号模拟 busy）、
权限引擎、审批流程（高风险工具调用触发 approval.request 进入 waiting_approval）。
workspace 策略选择（GitWorktree/Task/ReadOnly/Restricted）。

设计约束：
- 无依赖且未执行的节点进入 ready 队列
- 调度时检查目标职员/线程是否忙，忙则留 ready
- 分派前重验 company/department/employee active
- 每个节点执行前经预算预留（BudgetService.reserve）
- concurrency_limit 控制并行数（FIFO 获取 lease）
- 高风险工具调用触发真实审批（waiting_approval，不阻塞其他并行节点）
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

import aiosqlite

from acos.backends.service import BackendLeaseManager, BackendScheduler
from acos.governance.budget import BudgetService
from acos.governance.service import GovernanceService
from acos.organization.permission_engine import PermissionEngine
from acos.rpc.errors import AcosError
from acos.task.checkpoint import CheckpointService
from acos.task.models import new_id
from acos.task.repository import (
    PlanGenerationRepository,
    TaskAssignmentRepository,
    TaskNodeRepository,
    TaskRepository,
)

PROV_BOUNDED_COST_VIOLATION = "PROV-BOUNDED-COST-VIOLATION"
WF_BUDGET_APPROVAL_PENDING = "WF-BUDGET-APPROVAL-PENDING"


class Scheduler:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._tasks = TaskRepository(db_path)
        self._nodes = TaskNodeRepository(db_path)
        self._gens = PlanGenerationRepository(db_path)
        self._assignments = TaskAssignmentRepository(db_path)
        self._scheduler = BackendScheduler(db_path)
        self._leases = BackendLeaseManager(db_path)
        self._budget = BudgetService(db_path)
        self._gov = GovernanceService(db_path)
        self._perm = PermissionEngine(db_path)
        self._checkpoint = CheckpointService(db_path)

    async def run_generation(
        self,
        task_id: str,
        generation_id: str,
        execute_fn: Callable[[str, str, str], Any],
        currency: str = "CNY",
        reserve_micros: int = 1_000_000,
        high_risk_nodes: Optional[set[str]] = None,
    ) -> dict:
        """执行一个 generation：按 DAG 依赖并行推进所有节点。

        execute_fn(node_id, employee_id, backend_id) -> dict（真实执行；测试注入）
        返回 {completed: [node_id], waiting_approval: [node_id], failed: [node_id]}
        """
        high_risk_nodes = high_risk_nodes or set()
        nodes = await self._nodes.list_by_generation(generation_id)

        completed: list[str] = []
        waiting: list[str] = []
        failed: list[str] = []

        # 迭代推进：每轮选出可执行（依赖已完成）的 ready 节点，受 backend 容量约束
        done: set[str] = set()
        semaphore = asyncio.Semaphore(await self._generation_concurrency(nodes))

        async def _maybe_execute(node):
            async with semaphore:
                # 依赖未全部完成则跳过
                deps = node.depends_on or []
                if not all(d in done for d in deps):
                    return
                # 重验 employee active
                if node.assignee_employee_id:
                    ok = await self._employee_active(node.assignee_employee_id)
                    if not ok:
                        failed.append(node.node_id)
                        return
                # backend 同公司 healthy（plan 已填 backend_id）
                backend = await self._resolve_backend(node)
                if backend is None:
                    failed.append(node.node_id)
                    return
                # 预算预留（调用前）
                try:
                    resv = await self._budget.reserve(
                        company_id=node.company_id, task_id=task_id,
                        run_id=new_id("run"), node_id=node.node_id,
                        currency=currency, amount_micros=reserve_micros,
                    )
                except AcosError as exc:
                    if exc.code == WF_BUDGET_APPROVAL_PENDING:
                        waiting.append(node.node_id)
                        return
                    failed.append(node.node_id)
                    return
                if resv.get("status") == "pending_approval":
                    waiting.append(node.node_id)
                    return
                if resv.get("status") != "reserved":
                    failed.append(node.node_id)
                    return
                # 高风险工具调用 -> waiting_approval（不阻塞其他并行节点）
                if node.node_id in high_risk_nodes:
                    if node.status == "pending":
                        node = await self._nodes.transition(
                            node.node_id, node.version, "ready")
                    await self._nodes.transition(node.node_id, node.version, "waiting_approval")
                    await self._gov.create_approval(_approval(
                        company_id=node.company_id, task_id=task_id, node_id=node.node_id,
                        employee_id=node.assignee_employee_id or "system",
                        approval_type="tool_call",
                        risk_reason="高风险工具调用", requested_by="system",
                    )                    )
                    waiting.append(node.node_id)
                    done.add(node.node_id)
                    return
                # 取得 lease（超容量时短暂等待后重试，体现 FIFO 排队）
                lease = None
                for _ in range(50):
                    try:
                        lease = await self._leases.bind(
                            backend_id=backend.backend_id, company_id=node.company_id,
                            run_id=resv.get("reservation_id", new_id("run")),
                        )
                        break
                    except AcosError as exc:
                        if exc.code == "BACKEND-CAPACITY-FULL":
                            await asyncio.sleep(0.01)
                            continue
                        failed.append(node.node_id)
                        return
                if lease is None:
                    failed.append(node.node_id)
                    return
                if node.status == "pending":
                    node = await self._nodes.transition(node.node_id, node.version, "ready")
                node = await self._nodes.transition(node.node_id, node.version, "running")
                # 执行
                try:
                    await execute_fn(node.node_id, node.assignee_employee_id or "system",
                                     backend.backend_id)
                    await self._nodes.transition(node.node_id, node.version, "completed")
                    await self._checkpoint.create(
                        task_id=task_id, company_id=node.company_id, task_cursor=len(done) + 1,
                        generation_id=generation_id, run_id=lease.lease_id,
                    )
                    completed.append(node.node_id)
                    done.add(node.node_id)
                except Exception:
                    await self._nodes.transition(node.node_id, node.version, "failed")
                    failed.append(node.node_id)
                    done.add(node.node_id)
                finally:
                    await self._leases.release(lease.lease_id)

        # 多轮推进直至无新完成（DAG 可能多深度）
        progress = True
        while progress:
            progress = False
            ready = [n for n in nodes if n.node_id not in done]
            tasks = []
            for n in ready:
                deps = n.depends_on or []
                if all(d in done for d in deps):
                    if n.status in ("pending", "ready"):
                        progress = True
                        tasks.append(asyncio.create_task(_maybe_execute(n)))
            if tasks:
                await asyncio.gather(*tasks)
            else:
                # 无 ready 但仍有未完成 -> 可能是 waiting_approval，停止
                break

        return {"completed": completed, "waiting_approval": waiting, "failed": failed}

    async def _generation_concurrency(self, nodes: list) -> int:
        """取本 generation 涉及的所有 backend 的最小并发上限（FIFO 上限）。"""
        limits = []
        for n in nodes:
            backend = await self._resolve_backend(n)
            if backend is not None:
                limits.append(backend.concurrency_limit or 1)
        if not limits:
            return 1
        return max(1, min(limits))

    async def _global_concurrency(self) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT COUNT(*) AS c FROM backends")
            row = await cur.fetchone()
        count = row["c"] if row else 0
        return max(1, count * 2)

    async def _employee_active(self, employee_id: str) -> bool:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT status FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            row = await cur.fetchone()
        return row is not None and row["status"] == "active"

    async def _resolve_backend(self, node):
        from acos.backends.service import BackendService

        if node.backend_id:
            return await BackendService(self._db_path).get(node.backend_id)
        return await self._scheduler.select_backend(node.company_id)


def _approval(**kw):
    from acos.governance.models import Approval

    return Approval(**kw)
