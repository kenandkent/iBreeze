"""test_task_assignments：assignment 唯一索引 / close / list_active_task_ids（P9-T1a）。"""

from __future__ import annotations

import pytest

from acos.task.repository import (
    TaskAssignmentRepository,
    TaskNodeRepository,
    TaskRepository,
)
from tests.task.conftest import migrated_db, seed_company_employee


async def _mk_task(db):
    repo = TaskRepository(db)
    return await repo.create(await _mk_task_obj(repo))


async def _mk_task_obj(repo):
    from acos.task.models import Task

    return Task(task_id="task-a", company_id="co1", title="t", status="created",
                department_id="dep1", created_by_employee_id="emp1")


async def _mk_node(db, task_id):
    nodes = TaskNodeRepository(db)
    return await nodes.create(await _mk_node_obj(nodes, task_id))


async def _mk_node_obj(repo, task_id):
    from acos.task.models import TaskNode

    return TaskNode(node_id="node-a", task_id=task_id, company_id="co1", status="pending")


async def _mk_asg(db, task_id, employee_id, node_id):
    asg = TaskAssignmentRepository(db)
    return await asg.create(await _mk_asg_obj(asg, task_id, employee_id, node_id))


async def _mk_asg_obj(repo, task_id, employee_id, node_id):
    from acos.task.models import TaskAssignment

    return TaskAssignment(assignment_id="asg-a", task_id=task_id, employee_id=employee_id,
                          company_id="co1", node_id=node_id)


@pytest.mark.asyncio
async def test_create_and_close_assignment(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    task = await _mk_task(db)
    node = await _mk_node(db, task.task_id)
    a = await _mk_asg(db, task.task_id, "emp1", node.node_id)
    assert a.status == "active"
    closed = await TaskAssignmentRepository(db).close(a.assignment_id, a.version)
    assert closed.status == "closed"
    assert closed.active_until is not None


@pytest.mark.asyncio
async def test_unique_active_index_blocks_duplicate(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    task = await _mk_task(db)
    node = await _mk_node(db, task.task_id)
    a = await _mk_asg(db, task.task_id, "emp1", node.node_id)
    # 同 node_id+generation(空)+role 的第二个 active 应冲突（唯一索引）
    from acos.task.models import TaskAssignment

    dup = TaskAssignment(assignment_id="asg-b", task_id=task.task_id, employee_id="emp1",
                         company_id="co1", node_id=node.node_id)
    with pytest.raises(Exception):  # sqlite3.IntegrityError
        await TaskAssignmentRepository(db).create(dup)


@pytest.mark.asyncio
async def test_list_active_task_ids_filters_by_employee(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_company_employee(db, employee_id="emp2")
    task1 = await _mk_task(db)
    node1 = await _mk_node(db, task1.task_id)
    await _mk_asg(db, task1.task_id, "emp1", node1.node_id)
    # emp2 的 assignment 用不同节点，关闭后不应出现在 active 列表
    from acos.task.models import TaskAssignment, TaskNode

    node2 = await TaskNodeRepository(db).create(
        TaskNode(node_id="node-b", task_id=task1.task_id, company_id="co1", status="pending")
    )
    a2 = await TaskAssignmentRepository(db).create(
        TaskAssignment(assignment_id="asg-b", task_id=task1.task_id, employee_id="emp2",
                       company_id="co1", node_id=node2.node_id)
    )
    await TaskAssignmentRepository(db).close(a2.assignment_id, a2.version)

    repo = TaskAssignmentRepository(db)
    emp1_tasks = await repo.list_active_task_ids("emp1")
    emp2_tasks = await repo.list_active_task_ids("emp2")
    assert task1.task_id in emp1_tasks
    assert task1.task_id not in emp2_tasks
