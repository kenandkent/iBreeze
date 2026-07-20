"""test_workflow_methods：workflow.checkpoint.list / workflow.plan.validate / workflow.task.cancel（P9）。"""

from __future__ import annotations

import pytest

from acos.rpc.methods_workflow import WorkflowMethods
from acos.task.models import Task
from acos.task.repository import TaskRepository
from tests.task.conftest import (
    migrated_db, seed_backend, seed_budget_policy, seed_company_employee,
)


async def _mk_task(db, task_id, company="co1"):
    return await TaskRepository(db).create(Task(task_id=task_id, company_id=company,
                                                title="t", status="created",
                                                department_id="dep1",
                                                created_by_employee_id="emp1"))


@pytest.mark.asyncio
async def test_checkpoint_list_ok(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "task-wf")
    wf = WorkflowMethods(db)
    from acos.task.checkpoint import CheckpointService
    await CheckpointService(db).create(task_id="task-wf", company_id="co1", task_cursor=1)
    res = await wf._checkpoint_list({"task_id": "task-wf", "company_id": "co1"})
    assert res["items"]
    assert all("executor_state" not in it for it in res["items"])


@pytest.mark.asyncio
async def test_checkpoint_list_cross_company(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_company_employee(db, company_id="co2")
    await seed_backend(db)
    await _mk_task(db, "task-wf")
    wf = WorkflowMethods(db)
    with pytest.raises(Exception):
        await wf._checkpoint_list({"task_id": "task-wf", "company_id": "co2"})


@pytest.mark.asyncio
async def test_plan_validate_ok_and_fail(migrated_db):
    db = migrated_db
    await seed_company_employee(db, employee_id="emp1",
                                capability_snapshot='{"tools":[{"name":"read"}]}')
    await seed_backend(db)
    await seed_budget_policy(db)
    wf = WorkflowMethods(db)
    ok = await wf._plan_validate({
        "task_id": "t", "company_id": "co1", "manager_employee_id": "emp1",
        "manager_scope": "company",
        "dag": [{"node_id": "n1", "node_type": "agent_step", "goal": "g",
                 "depends_on": [], "assignee_employee_id": "emp1",
                 "workspace_strategy": "TaskWorkspace",
                 "outputs_schema": {"type": "object"}, "tools": ["read"]}],
    })
    assert ok["ok"] is True
    bad = await wf._plan_validate({
        "task_id": "t", "company_id": "co1", "manager_employee_id": "emp1",
        "manager_scope": "company",
        "dag": [{"node_id": "n1"}],
    })
    assert bad["ok"] is False
    assert bad["rule"] == "PV-01"


@pytest.mark.asyncio
async def test_task_cancel(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "task-wf")
    wf = WorkflowMethods(db)
    res = await wf._task_cancel({"task_id": "task-wf", "expected_version": 1})
    assert res["status"] == "cancelled"


@pytest.mark.asyncio
async def test_deadletter_resolve_ok(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "task-dl")
    import aiosqlite
    async with aiosqlite.connect(db) as c:
        await c.execute(
            """INSERT INTO dead_letters
               (dead_letter_id, company_id, task_id, node_id, reason, kind, status, version)
               VALUES ('dl1','co1','task-dl','n1','fix exhausted','fix_exhausted','open',1)"""
        )
        await c.commit()
    wf = WorkflowMethods(db)
    res = await wf._deadletter_resolve({"dead_letter_id": "dl1", "resolution": "resolved"})
    assert res["status"] == "resolved"
    assert res["task"]["task_id"] == "task-dl"
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status, version FROM dead_letters WHERE dead_letter_id='dl1'")
        row = await cur.fetchone()
        assert row["status"] == "resolved"
        assert row["version"] == 2


@pytest.mark.asyncio
async def test_deadletter_resolve_resumes_blocked_task(migrated_db):
    # 任务因 dead_letter 挂起（failed），resolved 应恢复为 running
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "task-dl-r")
    import aiosqlite
    async with aiosqlite.connect(db) as c:
        await c.execute(
            "UPDATE tasks SET status='failed', version=version+1 WHERE task_id='task-dl-r'"
        )
        await c.execute(
            """INSERT INTO dead_letters
               (dead_letter_id, company_id, task_id, node_id, reason, kind, status, version)
               VALUES ('dlr','co1','task-dl-r','n1','fix exhausted','fix_exhausted','open',1)"""
        )
        await c.commit()
    wf = WorkflowMethods(db)
    res = await wf._deadletter_resolve({"dead_letter_id": "dlr", "resolution": "resolved"})
    assert res["status"] == "resolved"
    assert res["task"]["status"] == "running"
    assert res["task"]["updated"] is True
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status FROM tasks WHERE task_id='task-dl-r'")
        assert (await cur.fetchone())["status"] == "running"


@pytest.mark.asyncio
async def test_deadletter_resolve_aborts_running_task(migrated_db):
    # 运行中的任务，aborted 应终止为 cancelled
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "task-dl-a")
    import aiosqlite
    async with aiosqlite.connect(db) as c:
        await c.execute(
            "UPDATE tasks SET status='running', version=version+1 WHERE task_id='task-dl-a'"
        )
        await c.execute(
            """INSERT INTO dead_letters
               (dead_letter_id, company_id, task_id, node_id, reason, kind, status, version)
               VALUES ('dla','co1','task-dl-a','n1','fix exhausted','fix_exhausted','open',1)"""
        )
        await c.commit()
    wf = WorkflowMethods(db)
    res = await wf._deadletter_resolve({"dead_letter_id": "dla", "resolution": "aborted"})
    assert res["status"] == "aborted"
    assert res["task"]["status"] == "cancelled"
    assert res["task"]["updated"] is True
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status FROM tasks WHERE task_id='task-dl-a'")
        assert (await cur.fetchone())["status"] == "cancelled"


@pytest.mark.asyncio
async def test_deadletter_resolve_not_open(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "task-dl2")
    import aiosqlite
    async with aiosqlite.connect(db) as c:
        await c.execute(
            """INSERT INTO dead_letters
               (dead_letter_id, company_id, task_id, reason, kind, status, version)
               VALUES ('dl2','co1','task-dl2','x','fix_exhausted','resolved',1)"""
        )
        await c.commit()
    wf = WorkflowMethods(db)
    with pytest.raises(Exception):
        await wf._deadletter_resolve({"dead_letter_id": "dl2", "resolution": "resolved"})


@pytest.mark.asyncio
async def test_deadletter_resolve_missing(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    wf = WorkflowMethods(db)
    with pytest.raises(Exception):
        await wf._deadletter_resolve({"dead_letter_id": "nope"})
