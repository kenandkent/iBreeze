"""test_parallel_review：多 lens 并发审查 + 结果并集（P9-T6）。"""

from __future__ import annotations

import asyncio

import pytest

from acos.task.models import Task
from acos.task.repository import TaskRepository
from acos.task.strategies_parallel_review import ParallelReviewStrategy
from tests.task.conftest import migrated_db, seed_backend, seed_company_employee


@pytest.mark.asyncio
async def test_parallel_review_union(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_company_employee(db, employee_id="emp2")
    await seed_backend(db)
    repo = TaskRepository(db)
    task = await repo.create(Task(task_id="task-r", company_id="co1", title="t",
                                  status="created", department_id="dep1",
                                  created_by_employee_id="emp1"))
    strategy = ParallelReviewStrategy(db)
    lenses = ["correctness", "security", "test_coverage"]
    target_nodes = ["n1", "n2"]
    calls = []

    async def reviewer_fn(lens, node_id, reviewer_id):
        calls.append((lens, node_id))
        await asyncio.sleep(0.01)
        return {"lens": lens, "node": node_id, "ok": True}

    union = await strategy.review(
        task_id=task.task_id, company_id="co1", generation_id="gen-x",
        target_nodes=target_nodes, reviewers=["emp1", "emp2"], lenses=lenses,
        reviewer_fn=reviewer_fn,
    )
    # 3 lens × 2 nodes = 6 并发调用
    assert len(calls) == 6
    assert set(union.keys()) == set(lenses)
    for lens in lenses:
        assert set(union[lens].keys()) == set(target_nodes)
    # 并发：不同 lens 的调用交错（非严格串行）——至少验证都完成
    assert all(v["ok"] for lens in lenses for v in union[lens].values())


@pytest.mark.asyncio
async def test_parallel_review_creates_reviewer_assignments(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_company_employee(db, employee_id="emp2")
    await seed_backend(db)
    repo = TaskRepository(db)
    task = await repo.create(Task(task_id="task-r2", company_id="co1", title="t",
                                  status="created", department_id="dep1",
                                  created_by_employee_id="emp1"))
    strategy = ParallelReviewStrategy(db)
    await strategy.review(
        task_id=task.task_id, company_id="co1", generation_id="gen-y",
        target_nodes=["n1"], reviewers=["emp1", "emp2"],
        lenses=["correctness", "security"], reviewer_fn=lambda l, n, r: {"ok": True},
    )
    from acos.task.repository import TaskAssignmentRepository

    asgs = await TaskAssignmentRepository(db).list_active_for_node(
        # 找到 review node
        (await TaskAssignmentRepository(db).list_by_task(task.task_id))[0].node_id, "reviewer")
    assert len(asgs) >= 1
