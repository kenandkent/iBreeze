"""test_planner：DAG 生成 / 拒绝模型 backend_id / plan_hash 确定性（P9-T3）。"""

from __future__ import annotations

import pytest

from acos.task.models import Task
from acos.task.planner import Planner, compute_plan_hash
from acos.task.repository import TaskNodeRepository, TaskRepository
from tests.task.conftest import (
    migrated_db, seed_backend, seed_budget_policy, seed_company_employee,
)


async def _make_task(db, task_id="task-p"):
    repo = TaskRepository(db)
    return await repo.create(Task(task_id=task_id, company_id="co1", title="t",
                                  status="created", department_id="dep1",
                                  created_by_employee_id="emp1"))


@pytest.mark.asyncio
async def test_generate_writes_generation_and_nodes(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    task = await _make_task(db)
    planner = Planner(db)

    async def chat(goal, acceptance):
        return [
            {"node_id": "n1", "node_type": "agent_step", "goal": "g1",
             "depends_on": [], "backend_id": "FAKE-BACKEND"},
            {"node_id": "n2", "node_type": "review_task", "goal": "g2",
             "depends_on": ["n1"]},
        ]

    gen = await planner.generate(
        task_id=task.task_id, company_id="co1", manager_employee_id="emp1",
        manager_scope="company", goal="goal", acceptance="acc", manager_chat=chat,
    )
    assert gen.status == "draft"
    # 节点已写入且 backend_id 被服务端覆盖（非模型伪造）
    nodes = await TaskNodeRepository(db).list_by_task(task.task_id)
    by_id = {n.node_id: n for n in nodes}
    assert by_id["n1"].backend_id == "be1"  # 服务端填充
    assert by_id["n2"].backend_id == "be1"
    assert len(nodes) == 2


@pytest.mark.asyncio
async def test_plan_hash_deterministic(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    dag_a = [
        {"node_id": "n1", "node_type": "agent_step", "goal": "g", "depends_on": ["n2"]},
        {"node_id": "n2", "node_type": "review_task", "goal": "r", "depends_on": []},
    ]
    dag_b = [
        {"node_id": "n2", "node_type": "review_task", "goal": "r", "depends_on": []},
        {"node_id": "n1", "node_type": "agent_step", "goal": "g", "depends_on": ["n2"]},
    ]
    planner = Planner(db)
    bm = await planner._resolve_backends("co1", dag_a)
    h1 = compute_plan_hash(dag_a, "co1", bm)
    h2 = compute_plan_hash(dag_b, "co1", bm)
    assert h1 == h2


@pytest.mark.asyncio
async def test_generate_twice_increments_generation_no(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    task = await _make_task(db)
    planner = Planner(db)

    async def chat(goal, acceptance):
        return [{"node_id": "n1", "node_type": "agent_step", "goal": "g"}]

    g1 = await planner.generate(task.task_id, "co1", "emp1", "company", "g", "a", chat)
    g2 = await planner.generate(task.task_id, "co1", "emp1", "company", "g", "a", chat)
    assert g2.generation_no == g1.generation_no + 1
