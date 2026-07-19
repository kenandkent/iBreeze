"""test_scheduler：DAG 并行 / 并发上限 / 高风险审批 / workspace 类型（P9-T5 红线）。"""

from __future__ import annotations

import asyncio

import pytest

from acos.task.models import Task, TaskNode
from acos.task.planner import Planner
from acos.task.repository import PlanGenerationRepository, TaskRepository
from acos.task.scheduler import Scheduler
from tests.task.conftest import (
    migrated_db, seed_backend, seed_budget_policy, seed_company_employee,
)


async def _make_task_and_gen(db, nodes_json, backend_per_node=None):
    repo = TaskRepository(db)
    task = await repo.create(Task(task_id="task-s", company_id="co1", title="t",
                                  status="created", department_id="dep1",
                                  created_by_employee_id="emp1"))
    planner = Planner(db)
    backend_per_node = backend_per_node or {}

    async def chat(goal, acceptance):
        return nodes_json

    gen = await planner.generate(task.task_id, "co1", "emp1", "company", "g", "a", chat)
    return task, gen


@pytest.mark.asyncio
async def test_parallel_execution_of_independent_nodes(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db, concurrency=4)
    await seed_budget_policy(db)
    nodes = [
        {"node_id": "n1", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"},
        {"node_id": "n2", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"},
        {"node_id": "n3", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"},
    ]
    task, gen = await _make_task_and_gen(db, nodes)
    order = []

    async def execute(node_id, emp, backend_id):
        order.append(node_id)
        await asyncio.sleep(0.02)

    sched = Scheduler(db)
    res = await sched.run_generation(task.task_id, gen.generation_id, execute)
    assert set(res["completed"]) == {"n1", "n2", "n3"}
    # 3 个独立节点应被并发启动（同一轮 gather）
    assert len(order) == 3


@pytest.mark.asyncio
async def test_dependent_node_waits(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db, concurrency=4)
    await seed_budget_policy(db)
    nodes = [
        {"node_id": "n1", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"},
        {"node_id": "n2", "node_type": "agent_step", "goal": "g",
         "depends_on": ["n1"], "assignee_employee_id": "emp1"},
    ]
    task, gen = await _make_task_and_gen(db, nodes)
    seq = []

    async def execute(node_id, emp, backend_id):
        seq.append(node_id)
        await asyncio.sleep(0.01)

    sched = Scheduler(db)
    res = await sched.run_generation(task.task_id, gen.generation_id, execute)
    assert res["completed"] == ["n1", "n2"]  # 顺序保证
    assert seq.index("n1") < seq.index("n2")


@pytest.mark.asyncio
async def test_high_risk_node_enters_waiting_approval(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db, concurrency=4)
    await seed_budget_policy(db)
    nodes = [
        {"node_id": "n1", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"},
        {"node_id": "n2", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"},
    ]
    task, gen = await _make_task_and_gen(db, nodes)
    executed = []

    async def execute(node_id, emp, backend_id):
        executed.append(node_id)

    sched = Scheduler(db)
    res = await sched.run_generation(
        task.task_id, gen.generation_id, execute,
        high_risk_nodes={"n2"},
    )
    assert "n1" in res["completed"]
    assert "n2" in res["waiting_approval"]
    assert "n2" not in executed
    # 其他并行节点不受影响
    assert "n1" in executed


@pytest.mark.asyncio
async def test_concurrency_limit_fifo(migrated_db):
    """backend concurrency=1 时，4 个独立节点串行执行（同一时刻最多 1 个 running）。"""
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db, concurrency=1)
    await seed_budget_policy(db)
    nodes = [
        {"node_id": f"n{i}", "node_type": "agent_step", "goal": "g",
         "depends_on": [], "assignee_employee_id": "emp1"}
        for i in range(4)
    ]
    task, gen = await _make_task_and_gen(db, nodes)
    concurrent = 0
    max_concurrent = 0

    async def execute(node_id, emp, backend_id):
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        await asyncio.sleep(0.03)
        concurrent -= 1

    sched = Scheduler(db)
    res = await sched.run_generation(task.task_id, gen.generation_id, execute)
    assert set(res["completed"]) == {f"n{i}" for i in range(4)}
    assert max_concurrent <= 1  # 受 lease 容量限制
