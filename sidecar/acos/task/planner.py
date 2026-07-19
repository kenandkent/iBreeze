"""Manager Plan 生成器（P9-T3）。

通过 Manager 职员（Capability Engine 装配运行配置 + Runtime 驱动一次对话）产出
自洽 DAG。Planner 拒绝模型输出中的任意 backend_id，由服务端按规则填充。
plan_hash 对相同 DAG 结构确定性一致。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from acos.backends.service import BackendScheduler
from acos.task.models import new_id
from acos.task.repository import PlanGenerationRepository, TaskNodeRepository

# DAG 节点 JSON Schema（受限子集，P9-T4 PV-01 复用）
NODE_SCHEMA_REQUIRED = ("node_id", "node_type", "goal")


def compute_plan_hash(dag: list[dict], company_id: str, backend_map: dict) -> str:
    """确定性：对任意等价 DAG 结构返回相同 hash。

    backend_id 纳入 hash（相同默认 Backend 变化时新 generation 得到新 hash）。
    """
    canonical = []
    for n in sorted(dag, key=lambda x: x.get("node_id", "")):
        canonical.append({
            "node_id": n.get("node_id"),
            "node_type": n.get("node_type"),
            "goal": n.get("goal"),
            "depends_on": sorted(n.get("depends_on", []) or []),
            "assignee_employee_id": n.get("assignee_employee_id"),
            "workspace_strategy": n.get("workspace_strategy"),
            "outputs_schema": n.get("outputs_schema"),
            "backend_id": backend_map.get(n.get("node_id")),
        })
    payload = json.dumps(
        {"company_id": company_id, "dag": canonical},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class Planner:
    """AI 生成 DAG（由注入的 manager 对话函数驱动）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._nodes = TaskNodeRepository(db_path)
        self._gens = PlanGenerationRepository(db_path)

    async def generate(
        self,
        task_id: str,
        company_id: str,
        manager_employee_id: str,
        manager_scope: str,
        goal: str,
        acceptance: str,
        manager_chat: Any,  # async (prompt: str) -> list[dict]，由测试注入
        department_id: Optional[str] = None,
    ) -> Any:
        """生成新 plan generation 并写入 task_node（状态 pending）。

        返回 PlanGeneration。生成后状态为 draft（待校验），不进入执行。
        """
        # 1) 调用 Manager 产出 DAG（模型可能伪造 backend_id，此处仅作为草稿）
        raw_dag = await manager_chat(goal, acceptance)

        # 2) 服务端填充 backend_id（拒绝模型携带的 backend_id）
        backend_map = await self._resolve_backends(company_id, raw_dag)
        for n in raw_dag:
            n.pop("backend_id", None)  # 绝不信任模型输出

        plan_hash = compute_plan_hash(raw_dag, company_id, backend_map)

        # 3) generation_no：基于已有代数 +1
        existing = await self._gens.list_by_task(task_id)
        generation_no = len(existing) + 1
        generation_id = new_id("gen")
        gen = await self._gens.create(_gen(
            generation_id=generation_id, task_id=task_id, company_id=company_id,
            generation_no=generation_no, plan_hash=plan_hash,
            dag_json=json.dumps(raw_dag, ensure_ascii=False),
            created_by_employee_id=manager_employee_id,
            status="draft",
        ))

        # 4) 写入 task_node（pending，待调度）；重新规划时清理旧草稿节点
        await self._nodes.delete_pending_for_task(task_id)
        for n in raw_dag:
            node_id = n.get("node_id") or new_id("node")
            await self._nodes.create(_node(
                node_id=node_id, task_id=task_id, company_id=company_id,
                node_type=n.get("node_type", "agent_step"),
                assignee_employee_id=n.get("assignee_employee_id"),
                generation_id=generation_id,
                backend_id=backend_map.get(node_id),
                depends_on=n.get("depends_on", []) or [],
                workspace_strategy=n.get("workspace_strategy"),
                outputs_schema=n.get("outputs_schema"),
                goal=n.get("goal"),
                status="pending",
            ))

        return gen

    async def _resolve_backends(self, company_id: str, dag: list[dict]) -> dict:
        """为 agent/review/fix/merge 节点服务端填充同公司可调度 Backend。"""
        scheduler = BackendScheduler(self._db_path)
        backend = await scheduler.select_backend(company_id)
        default_backend_id = backend.backend_id if backend else None
        result = {}
        for n in dag:
            nt = n.get("node_type")
            if nt in ("agent_step", "review_task", "fix", "merge"):
                result[n.get("node_id")] = default_backend_id
            else:
                result[n.get("node_id")] = None  # manual_task/condition 必须 NULL
        return result


def _gen(**kw):  # 简化构造
    from acos.task.models import PlanGeneration

    return PlanGeneration(**kw)


def _node(**kw):
    from acos.task.models import TaskNode

    return TaskNode(**kw)
