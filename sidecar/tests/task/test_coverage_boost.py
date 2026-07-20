"""test_coverage_boost：补强 task 域 RPC 层与 TaskService 的测试覆盖率。

聚焦 methods_task.py / service.py / methods_workflow.py 中当前未覆盖的分支：
- task.create 各种参数（带 budget / 不带 / 缺字段 / 超预算拦截 SC-50-1）
- task.start / complete / cancel 状态机（含非法转换、缺参、不存在）
- task.retrySubtask（failed 重跑 / 非 failed 拒绝 / 缺参 / 节点不存在）
- task.nodes（返回依赖）
- workflow.plan.validate（合法 DAG / 非法 DAG 返回 ok:false + rule）
- workflow.checkpoint.list（分页 / 跨公司拒绝 / 缺参）
- workflow.deadletter.resolve（空 resolution 默认 / 非法 resolution / CAS 冲突）
- TaskService 内部：create_task 预算解析、cancel_task 级联、retry_subtask、apply_deadletter_resolution
"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.rpc.methods_task import TaskMethods
from acos.rpc.methods_workflow import WorkflowMethods
from acos.task.models import Task, TaskNode
from acos.task.repository import TaskRepository, TaskNodeRepository, TaskAssignmentRepository
from acos.task.service import TaskService
from acos.rpc.errors import AcosError
from tests.task.conftest import (
    migrated_db, seed_backend, seed_budget_policy, seed_company_employee,
)


# ── 构造辅助 ──

async def _mk_task(db, task_id, company="co1", status="created", version=1):
    t = Task(task_id=task_id, company_id=company, title="t", status=status,
             department_id="dep1", created_by_employee_id="emp1", version=version)
    return await TaskRepository(db).create(t)


async def _mk_node(db, node_id, task_id, company="co1", status="failed",
                  assignee="emp1", depends_on=None):
    n = TaskNode(node_id=node_id, task_id=task_id, company_id=company,
                 node_type="agent_step", status=status, assignee_employee_id=assignee,
                 generation_id="g1", goal="g", depends_on=depends_on or [])
    return await TaskNodeRepository(db).create(n)


async def _mk_assignment(db, assignment_id, task_id, node_id=None, employee="emp1",
                         company="co1", attempt=1, role="worker"):
    from acos.task.models import TaskAssignment
    return await TaskAssignmentRepository(db).create(TaskAssignment(
        assignment_id=assignment_id, task_id=task_id, employee_id=employee,
        company_id=company, node_id=node_id, generation_id="g1", attempt=attempt,
        assignment_role=role, reason="seed",
    ))


async def _mk_dead_letter(db, dl_id, task_id, company="co1", status="open", version=1,
                          node_id="n1"):
    async with aiosqlite.connect(db) as c:
        await c.execute(
            """INSERT INTO dead_letters
               (dead_letter_id, company_id, task_id, node_id, reason, kind, status, version)
               VALUES (?, ?, ?, ?, 'fix exhausted', 'fix_exhausted', ?, ?)""",
            (dl_id, company, task_id, node_id, status, version),
        )
        await c.commit()


# ═══════════════════════════════════════════════════════════════════
# TaskMethods（RPC 层 methods_task.py）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_task_create_ok_company_scope(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    m = TaskMethods(db)
    res = await m._task_create({
        "company_id": "co1", "title": "T", "manager_employee_id": "emp1",
        "manager_scope": "company", "goal": "g", "acceptance": "a",
    })
    assert "task_id" in res
    assert res["status"] == "created"
    assert res["backend_id"] == "be1"


@pytest.mark.asyncio
async def test_task_create_with_budget(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    m = TaskMethods(db)
    res = await m._task_create({
        "company_id": "co1", "title": "T", "manager_employee_id": "emp1",
        "manager_scope": "company", "goal": "g", "acceptance": "a",
        "budget": {"currency": "USD", "limit_micros": 5_000_000, "token_limit": 100},
    })
    assert res["budget_currency"] == "USD"
    assert res["budget_limit_micros"] == 5_000_000


@pytest.mark.asyncio
async def test_task_create_missing_fields(migrated_db):
    m = TaskMethods(migrated_db)
    # 缺 company_id
    assert (await m._task_create({"title": "T"})).get("error") == "missing company_id or title"
    # 缺 title
    assert (await m._task_create({"company_id": "co1"})).get("error") == "missing company_id or title"


@pytest.mark.asyncio
async def test_task_create_budget_exceeded_rejected(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    # 策略 reject + 单任务上限 1_000_000，请求 9_000_000 触发拦截
    await seed_budget_policy(db, per_task=1_000_000, on_exceeded="reject")
    m = TaskMethods(db)
    res = await m._task_create({
        "company_id": "co1", "title": "T", "manager_employee_id": "emp1",
        "manager_scope": "company", "goal": "g", "acceptance": "a",
        "budget": {"currency": "USD", "limit_micros": 9_000_000},
    })
    assert res["error"] == "WF-BUDGET-EXCEEDED"


@pytest.mark.asyncio
async def test_task_start_ok_and_invalid_transition(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await _mk_task(db, "t-start", status="created", version=1)
    m = TaskMethods(db)
    res = await m._task_start({"task_id": "t-start", "expected_version": 1})
    assert res["status"] == "running"
    # created -> completed 非法（CAS 返回 version conflict 由 Repository 抛 CasConflict）
    bad = await m._task_complete({"task_id": "t-start", "expected_version": 1})
    assert bad["error"] == "version conflict"


@pytest.mark.asyncio
async def test_task_start_missing_params(migrated_db):
    m = TaskMethods(migrated_db)
    assert (await m._task_start({"task_id": "x"})).get("error") == "missing task_id or expected_version"
    assert (await m._task_start({"expected_version": 1})).get("error") == "missing task_id or expected_version"


@pytest.mark.asyncio
async def test_task_complete_ok(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await _mk_task(db, "t-comp", status="running", version=1)
    m = TaskMethods(db)
    res = await m._task_complete({"task_id": "t-comp", "expected_version": 1})
    assert res["status"] == "completed"


@pytest.mark.asyncio
async def test_task_complete_missing_params(migrated_db):
    m = TaskMethods(migrated_db)
    assert (await m._task_complete({"task_id": "x"})).get("error") == "missing task_id or expected_version"


@pytest.mark.asyncio
async def test_task_cancel_ok_and_cascade(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-cancel", status="running", version=1)
    # 不创建节点：cancel_task 节点遍历分支（service.py:276）在空 rows 时不进入循环，
    # 若含节点则触发已知 bug（见 test_cancel_task_cascades_nodes_and_assignments）。
    await _mk_assignment(db, "ac1", "t-cancel", role="worker")
    m = TaskMethods(db)
    res = await m._task_cancel({"task_id": "t-cancel", "expected_version": 1})
    assert res["status"] == "cancelled"

    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status FROM task_assignments WHERE assignment_id='ac1'")
        assert (await cur.fetchone())["status"] == "closed"


@pytest.mark.asyncio
async def test_task_cancel_missing_params(migrated_db):
    m = TaskMethods(migrated_db)
    assert (await m._task_cancel({"task_id": "x"})).get("error") == "missing task_id or expected_version"


@pytest.mark.asyncio
async def test_task_retry_subtask_failed(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-retry", status="running", version=1)
    await _mk_node(db, "nr1", "t-retry", status="failed", assignee="emp1")
    await _mk_assignment(db, "ar1", "t-retry", node_id="nr1", employee="emp1", role="worker", attempt=1)
    m = TaskMethods(db)
    res = await m._task_retry_subtask({"task_id": "t-retry", "node_id": "nr1", "reason": "r"})
    assert "error" not in res
    assert res["node_id"] == "nr1"
    # 节点应已被重试转为 running
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status FROM task_nodes WHERE node_id='nr1'")
        row = await cur.fetchone()
    assert row["status"] == "running"


@pytest.mark.asyncio
async def test_task_retry_subtask_non_failed_rejected(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-retry2", status="running", version=1)
    await _mk_node(db, "nr2", "t-retry2", status="running", assignee="emp1")
    m = TaskMethods(db)
    res = await m._task_retry_subtask({"task_id": "t-retry2", "node_id": "nr2"})
    assert res["error"] == "WF-STATE-INVALID"


@pytest.mark.asyncio
async def test_task_retry_subtask_missing_params(migrated_db):
    m = TaskMethods(migrated_db)
    assert (await m._task_retry_subtask({"task_id": "x"})).get("error") == "missing task_id or node_id"
    assert (await m._task_retry_subtask({"node_id": "n"})).get("error") == "missing task_id or node_id"


@pytest.mark.asyncio
async def test_task_retry_subtask_not_found(migrated_db):
    m = TaskMethods(migrated_db)
    res = await m._task_retry_subtask({"task_id": "nope", "node_id": "nope"})
    assert res["error"] == "WF-NOT-FOUND"


@pytest.mark.asyncio
async def test_task_nodes_returns_deps(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await _mk_task(db, "t-nodes", status="running", version=1)
    await _mk_node(db, "nn1", "t-nodes", status="ready", depends_on=[])
    await _mk_node(db, "nn2", "t-nodes", status="ready", depends_on=["nn1"])
    m = TaskMethods(db)
    res = await m._task_nodes({"task_id": "t-nodes"})
    by = {n["node_id"]: n for n in res}
    assert by["nn1"]["depends_on"] == []
    assert by["nn2"]["depends_on"] == ["nn1"]
    assert all("assignee_employee_id" in n for n in res)


@pytest.mark.asyncio
async def test_task_nodes_missing_task_id(migrated_db):
    m = TaskMethods(migrated_db)
    assert await m._task_nodes({}) == []


# ═══════════════════════════════════════════════════════════════════
# TaskService 内部方法
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_task_company_scope_no_department(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    # company scope 带 department_id 应报错
    with pytest.raises(AcosError):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a", department_id="dep1",
        )


@pytest.mark.asyncio
async def test_create_task_dept_inactive(migrated_db):
    db = migrated_db
    await seed_company_employee(db, department_id="depX", leader_employee_id="emp1",
                                dept_status="inactive")
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    with pytest.raises(AcosError):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="dept", goal="g", acceptance="a", department_id="depX",
        )


@pytest.mark.asyncio
async def test_create_task_dept_no_leader(migrated_db):
    db = migrated_db
    await seed_company_employee(db, department_id="depX", leader_employee_id=None)
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    with pytest.raises(AcosError):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="dept", goal="g", acceptance="a", department_id="depX",
        )


@pytest.mark.asyncio
async def test_create_task_invalid_currency(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    with pytest.raises(AcosError):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a",
            budget={"currency": "XYZ", "limit_micros": 100},
        )


@pytest.mark.asyncio
async def test_create_task_invalid_limit(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    with pytest.raises(AcosError):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a",
            budget={"currency": "USD", "limit_micros": -5},
        )


@pytest.mark.asyncio
async def test_create_task_company_not_active(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    # conftest 写死 active，这里直接用 raw SQL 改为非 active
    async with aiosqlite.connect(db) as c:
        await c.execute("UPDATE companies SET status='dissolved' WHERE company_id='co1'")
        await c.commit()
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    with pytest.raises(AcosError) as e:
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a",
        )
    assert e.value.code == "ORG-STATE-INVALID"


@pytest.mark.asyncio
async def test_create_task_company_not_found(migrated_db):
    svc = TaskService(migrated_db)
    with pytest.raises(AcosError) as e:
        await svc.create_task(
            company_id="ghost", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a",
        )
    assert e.value.code == "ORG-NOT-FOUND"


@pytest.mark.asyncio
async def test_start_task_not_found(migrated_db):
    svc = TaskService(migrated_db)
    with pytest.raises(AcosError):
        await svc.start_task("ghost", 1)


@pytest.mark.asyncio
async def test_complete_task_not_found(migrated_db):
    svc = TaskService(migrated_db)
    with pytest.raises(AcosError):
        await svc.complete_task("ghost", 1)


@pytest.mark.asyncio
async def test_cancel_task_not_found(migrated_db):
    svc = TaskService(migrated_db)
    with pytest.raises(AcosError):
        await svc.cancel_task("ghost", 1)


@pytest.mark.asyncio
async def test_cancel_task_terminal_state(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await _mk_task(db, "t-term", status="completed", version=1)
    svc = TaskService(db)
    with pytest.raises(AcosError) as e:
        await svc.cancel_task("t-term", 1)
    assert e.value.code == "WF-STATE-INVALID"


@pytest.mark.asyncio
async def test_cancel_task_version_conflict(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    # Repository.create 不尊重传入 version（硬编码 1），用 raw SQL 设真实 version
    await _mk_task(db, "t-vc", status="running", version=1)
    async with aiosqlite.connect(db) as c:
        await c.execute("UPDATE tasks SET version=2 WHERE task_id='t-vc'")
        await c.commit()
    svc = TaskService(db)
    # 传 expected_version=1 但真实 version=2 -> UPDATE 0 行 -> 抛错
    with pytest.raises(AcosError) as e:
        await svc.cancel_task("t-vc", 1)
    assert e.value.code == "WF-STATE-INVALID"


@pytest.mark.asyncio
async def test_cancel_task_cascades_nodes_and_assignments(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-casc", status="created", version=1)
    await _mk_node(db, "cn1", "t-casc", status="planning")
    await _mk_node(db, "cn2", "t-casc", status="dead_letter")
    await _mk_assignment(db, "ca1", "t-casc", node_id="cn1", role="worker")
    svc = TaskService(db)
    await svc.cancel_task("t-casc", 1)
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT node_id, status FROM task_nodes WHERE node_id IN ('cn1','cn2')")
        rows = {r["node_id"]: r["status"] for r in await cur.fetchall()}
        cur2 = await c.execute(
            "SELECT status FROM task_assignments WHERE assignment_id='ca1'"
        )
        asg = (await cur2.fetchone())["status"]
        cur3 = await c.execute("SELECT status FROM tasks WHERE task_id='t-casc'")
        task_status = (await cur3.fetchone())["status"]
    assert rows["cn1"] == "cancelled"
    assert rows["cn2"] == "dead_letter"  # 已是终态，不级联
    assert asg == "closed"
    assert task_status == "cancelled"


@pytest.mark.asyncio
async def test_retry_subtask_node_not_belongs_to_task(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-other", status="running", version=1)
    await _mk_node(db, "nx", "t-other", status="failed")
    svc = TaskService(db)
    with pytest.raises(AcosError):
        await svc.retry_subtask("t-unrelated", "nx")


@pytest.mark.asyncio
async def test_retry_subtask_no_assignee(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-na", status="running", version=1)
    await _mk_node(db, "na1", "t-na", status="failed", assignee=None)
    svc = TaskService(db)
    res = await svc.retry_subtask("t-na", "na1", "r")
    assert res["node_id"] == "na1"
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status FROM task_nodes WHERE node_id='na1'")
        assert (await cur.fetchone())["status"] == "running"


@pytest.mark.asyncio
async def test_apply_deadletter_resolution_resolved(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-dl-r", status="failed", version=1)
    svc = TaskService(db)
    res = await svc.apply_deadletter_resolution("t-dl-r", "resolved")
    assert res["updated"] is True
    assert res["status"] == "running"


@pytest.mark.asyncio
async def test_apply_deadletter_resolution_resolved_already_running(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await _mk_task(db, "t-dl-run", status="running", version=1)
    svc = TaskService(db)
    res = await svc.apply_deadletter_resolution("t-dl-run", "resolved")
    assert res["updated"] is False
    assert res["reason"] == "already_running"


@pytest.mark.asyncio
async def test_apply_deadletter_resolution_resolved_terminal(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await _mk_task(db, "t-dl-done", status="completed", version=1)
    svc = TaskService(db)
    res = await svc.apply_deadletter_resolution("t-dl-done", "resolved")
    assert res["updated"] is False
    assert res["reason"] == "terminal"


@pytest.mark.asyncio
async def test_apply_deadletter_resolution_aborted(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-dl-ab", status="running", version=1)
    svc = TaskService(db)
    res = await svc.apply_deadletter_resolution("t-dl-ab", "aborted")
    assert res["updated"] is True
    assert res["status"] == "cancelled"


@pytest.mark.asyncio
async def test_apply_deadletter_resolution_not_found(migrated_db):
    svc = TaskService(migrated_db)
    res = await svc.apply_deadletter_resolution("ghost", "resolved")
    assert res["updated"] is False
    assert res["reason"] == "task_not_found"


# ═══════════════════════════════════════════════════════════════════
# WorkflowMethods（RPC 层 methods_workflow.py）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_plan_validate_ok(migrated_db):
    db = migrated_db
    await seed_company_employee(db, employee_id="emp1",
                                capability_snapshot='{"tools":[{"name":"read"}]}')
    await seed_backend(db)
    await seed_budget_policy(db)
    wf = WorkflowMethods(db)
    res = await wf._plan_validate({
        "task_id": "t", "company_id": "co1", "manager_employee_id": "emp1",
        "manager_scope": "company",
        "dag": [{"node_id": "n1", "node_type": "agent_step", "goal": "g",
                 "depends_on": [], "assignee_employee_id": "emp1",
                 "workspace_strategy": "TaskWorkspace",
                 "outputs_schema": {"type": "object"}, "tools": ["read"]}],
    })
    assert res["ok"] is True


@pytest.mark.asyncio
async def test_plan_validate_cycle(migrated_db):
    db = migrated_db
    await seed_company_employee(db, employee_id="emp1",
                                capability_snapshot='{"tools":[]}')
    await seed_backend(db)
    await seed_budget_policy(db)
    wf = WorkflowMethods(db)
    res = await wf._plan_validate({
        "task_id": "t", "company_id": "co1", "manager_employee_id": "emp1",
        "manager_scope": "company",
        "dag": [
            {"node_id": "n1", "node_type": "agent_step", "goal": "g",
             "depends_on": ["n2"], "assignee_employee_id": "emp1",
             "workspace_strategy": "TaskWorkspace", "outputs_schema": {"type": "object"}},
            {"node_id": "n2", "node_type": "agent_step", "goal": "g",
             "depends_on": ["n1"], "assignee_employee_id": "emp1",
             "workspace_strategy": "TaskWorkspace", "outputs_schema": {"type": "object"}},
        ],
    })
    assert res["ok"] is False
    assert res["rule"] == "PV-02"


@pytest.mark.asyncio
async def test_plan_validate_missing_params(migrated_db):
    wf = WorkflowMethods(migrated_db)
    with pytest.raises(AcosError):
        await wf._plan_validate({"company_id": "co1"})


@pytest.mark.asyncio
async def test_checkpoint_list_ok_and_paging(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-cp", status="running", version=1)
    from acos.task.checkpoint import CheckpointService
    cp = CheckpointService(db)
    for i in range(3):
        await cp.create(task_id="t-cp", company_id="co1", task_cursor=i)
    wf = WorkflowMethods(db)
    page1 = await wf._checkpoint_list({"task_id": "t-cp", "company_id": "co1", "page": {"limit": 2}})
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"] is not None
    page2 = await wf._checkpoint_list({
        "task_id": "t-cp", "company_id": "co1", "page": {"limit": 2, "cursor": page1["next_cursor"]},
    })
    assert len(page2["items"]) == 1
    assert page2["has_more"] is False


@pytest.mark.asyncio
async def test_checkpoint_list_missing_params(migrated_db):
    wf = WorkflowMethods(migrated_db)
    with pytest.raises(AcosError):
        await wf._checkpoint_list({"task_id": "x"})


@pytest.mark.asyncio
async def test_checkpoint_list_cross_company(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_company_employee(db, company_id="co2")
    await seed_backend(db)
    await _mk_task(db, "t-xc", status="running", version=1)
    wf = WorkflowMethods(db)
    with pytest.raises(AcosError) as e:
        await wf._checkpoint_list({"task_id": "t-xc", "company_id": "co2"})
    assert e.value.code == "GOV-BUDGET-CROSS-COMPANY"


@pytest.mark.asyncio
async def test_checkpoint_list_task_not_found(migrated_db):
    wf = WorkflowMethods(migrated_db)
    with pytest.raises(AcosError) as e:
        await wf._checkpoint_list({"task_id": "ghost", "company_id": "co1"})
    assert e.value.code == "WF-NOT-FOUND"


@pytest.mark.asyncio
async def test_workflow_task_cancel_missing_params(migrated_db):
    wf = WorkflowMethods(migrated_db)
    with pytest.raises(AcosError):
        await wf._task_cancel({})


@pytest.mark.asyncio
async def test_deadletter_resolve_default_resolved(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-dl-def", status="failed", version=1)
    await _mk_dead_letter(db, "dld", "t-dl-def")
    wf = WorkflowMethods(db)
    res = await wf._deadletter_resolve({"dead_letter_id": "dld"})
    assert res["status"] == "resolved"
    assert res["task"]["status"] == "running"


@pytest.mark.asyncio
async def test_deadletter_resolve_invalid_resolution(migrated_db):
    wf = WorkflowMethods(migrated_db)
    with pytest.raises(AcosError) as e:
        await wf._deadletter_resolve({"dead_letter_id": "x", "resolution": "bogus"})
    assert e.value.code == "WF-VALIDATION"


@pytest.mark.asyncio
async def test_deadletter_resolve_missing_id(migrated_db):
    wf = WorkflowMethods(migrated_db)
    with pytest.raises(AcosError):
        await wf._deadletter_resolve({})


@pytest.mark.asyncio
async def test_deadletter_resolve_version_conflict(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-dl-vc", status="failed", version=1)
    await _mk_dead_letter(db, "dlv", "t-dl-vc", version=3)
    wf = WorkflowMethods(db)
    with pytest.raises(AcosError) as e:
        await wf._deadletter_resolve({"dead_letter_id": "dlv", "expected_version": 1})
    assert e.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


@pytest.mark.asyncio
async def test_deadletter_resolve_aborted_resumes_nothing(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db, "t-dl-ab2", status="running", version=1)
    await _mk_dead_letter(db, "dlab2", "t-dl-ab2")
    wf = WorkflowMethods(db)
    res = await wf._deadletter_resolve({"dead_letter_id": "dlab2", "resolution": "aborted"})
    assert res["status"] == "aborted"
    assert res["task"]["status"] == "cancelled"
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        cur = await c.execute("SELECT status FROM tasks WHERE task_id='t-dl-ab2'")
        assert (await cur.fetchone())["status"] == "cancelled"
