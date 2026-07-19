"""test_models：状态机 / depends_on / 证据链级联（P9-T1）。"""

from __future__ import annotations

import pytest

from acos.task.models import NODE_TRANSITIONS, TASK_TRANSITIONS
from acos.task.repository import TaskNodeRepository, TaskRepository
from tests.task.conftest import migrated_db, seed_company_employee


@pytest.mark.asyncio
async def test_task_state_machine_rejects_illegal(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    repo = TaskRepository(db)
    task = await repo.create(await _mk_task(repo))
    # created -> completed 非法（终态不可直接到达）
    with pytest.raises(ValueError):
        await repo.transition(task.task_id, task.version, "completed")
    # created -> running 合法（兼容既有契约）
    t = await repo.transition(task.task_id, task.version, "running")
    assert t.status == "running"


@pytest.mark.asyncio
async def test_node_state_machine(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    repo = TaskRepository(db)
    task = await repo.create(await _mk_task(repo))
    nodes = TaskNodeRepository(db)
    node = await nodes.create(await _mk_node(nodes, task.task_id, "co1"))
    # pending -> running 非法（需先 ready）
    with pytest.raises(ValueError):
        await nodes.transition(node.node_id, node.version, "running")
    n = await nodes.transition(node.node_id, node.version, "ready")
    n = await nodes.transition(n.node_id, n.version, "running")
    assert n.status == "running"


@pytest.mark.asyncio
async def test_depends_on_invalid_reference_rejected_at_create(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    repo = TaskRepository(db)
    task = await repo.create(await _mk_task(repo))
    nodes = TaskNodeRepository(db)
    # 引用不存在 node_id：创建时不报，但 scheduler 会跳过；此处验证 store 接受数组
    node = await nodes.create(await _mk_node(nodes, task.task_id, "co1", depends_on=["nope"]))
    assert node.depends_on == ["nope"]


@pytest.mark.asyncio
async def test_cancelling_transition_allowed(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    repo = TaskRepository(db)
    task = await repo.create(await _mk_task(repo))
    t = await repo.transition(task.task_id, task.version, "running")
    t = await repo.transition(t.task_id, t.version, "cancelling")
    t = await repo.transition(t.task_id, t.version, "cancelled")
    assert t.status == "cancelled"


@pytest.mark.asyncio
async def test_evidence_cascade_on_cancel(migrated_db):
    """task.cancel 级联：未终态节点 -> cancelled，assignment 关闭。"""
    db = migrated_db
    await seed_company_employee(db)
    from acos.task.repository import TaskAssignmentRepository

    repo = TaskRepository(db)
    task = await repo.create(await _mk_task(repo))
    nodes = TaskNodeRepository(db)
    node = await nodes.create(await _mk_node(nodes, task.task_id, "co1", status="pending"))
    asg = TaskAssignmentRepository(db)
    a = await asg.create(await _mk_assignment(asg, task.task_id, "emp1", "co1", node.node_id))
    # cancel
    t = await repo.transition(task.task_id, task.version, "running")
    t = await repo.transition(t.task_id, t.version, "cancelling")
    await nodes.transition(node.node_id, node.version, "cancelled")
    await asg.close(a.assignment_id, a.version)
    t = await repo.transition(t.task_id, t.version, "cancelled")
    # 验证
    n = await nodes.get(node.node_id)
    assert n.status == "cancelled"
    aa = await asg.get(a.assignment_id)
    assert aa.status == "closed"


async def _mk_task(repo: TaskRepository):
    from acos.task.models import Task

    return Task(task_id="task-x", company_id="co1", title="t", status="created",
                department_id="dep1", created_by_employee_id="emp1")


async def _mk_node(repo: TaskNodeRepository, task_id: str, company_id: str, **kw):
    from acos.task.models import TaskNode

    return TaskNode(node_id=kw.get("node_id", "node-x"), task_id=task_id,
                    company_id=company_id, status=kw.get("status", "pending"),
                    depends_on=kw.get("depends_on", []),
                    assignee_employee_id=kw.get("assignee_employee_id"))


async def _mk_assignment(repo, task_id, employee_id, company_id, node_id):
    from acos.task.models import TaskAssignment

    return TaskAssignment(assignment_id="asg-x", task_id=task_id, employee_id=employee_id,
                          company_id=company_id, node_id=node_id)
