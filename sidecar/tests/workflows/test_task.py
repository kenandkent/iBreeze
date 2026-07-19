"""Task / TaskNode / TaskRun 服务测试。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import pytest

from acos.store.migrator import Migrator
from acos.workflows.models import Task, TaskAssignment, TaskNode, TaskRun
from acos.workflows.service import (
    CasConflict,
    TaskAssignmentService,
    TaskNodeService,
    TaskRunService,
    TaskService,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(p)


@pytest.fixture
def task_svc(db_path: str) -> TaskService:
    return TaskService(db_path)


@pytest.fixture
def node_svc(db_path: str) -> TaskNodeService:
    return TaskNodeService(db_path)


@pytest.fixture
def run_svc(db_path: str) -> TaskRunService:
    return TaskRunService(db_path)


@pytest.fixture
def assign_svc(db_path: str) -> TaskAssignmentService:
    return TaskAssignmentService(db_path)


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_task(**extra: object) -> Task:
    data: dict = {
        "task_id": f"task-{_uid()}",
        "company_id": "comp-1",
        "title": "Test Task",
        "description": "desc",
    }
    data.update(extra)  # type: ignore[arg-type]
    return Task(**data)


def _make_node(task_id: str, **extra: object) -> TaskNode:
    data: dict = {
        "node_id": f"node-{_uid()}",
        "task_id": task_id,
        "company_id": "comp-1",
    }
    data.update(extra)  # type: ignore[arg-type]
    return TaskNode(**data)


def _make_run(node_id: str, task_id: str, **extra: object) -> TaskRun:
    data: dict = {
        "run_id": f"run-{_uid()}",
        "node_id": node_id,
        "task_id": task_id,
        "company_id": "comp-1",
    }
    data.update(extra)  # type: ignore[arg-type]
    return TaskRun(**data)


# ── Task ──


async def test_create_and_get_task(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)

    fetched = await task_svc.get_task(task.task_id)
    assert fetched is not None
    assert fetched.title == "Test Task"
    assert fetched.status == "created"
    assert fetched.version == 1


async def test_list_tasks_by_company(task_svc: TaskService) -> None:
    await task_svc.create_task(_make_task(company_id="comp-A", title="A1"))
    await task_svc.create_task(_make_task(company_id="comp-A", title="A2"))
    await task_svc.create_task(_make_task(company_id="comp-B", title="B1"))

    a_list = await task_svc.list_tasks("comp-A")
    assert len(a_list) == 2
    b_list = await task_svc.list_tasks("comp-B")
    assert len(b_list) == 1


async def test_list_tasks_by_status(task_svc: TaskService) -> None:
    await task_svc.create_task(_make_task(title="t1"))
    t2 = _make_task(title="t2")
    await task_svc.create_task(t2)
    await task_svc.start_task(t2.task_id, 1)

    created = await task_svc.list_tasks("comp-1", status="created")
    assert len(created) == 1
    running = await task_svc.list_tasks("comp-1", status="running")
    assert len(running) == 1


async def test_task_lifecycle(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)

    started = await task_svc.start_task(task.task_id, 1)
    assert started.status == "running"
    assert started.version == 2

    completed = await task_svc.complete_task(task.task_id, 2)
    assert completed.status == "completed"
    assert completed.version == 3


async def test_task_cancel_from_created(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)

    cancelled = await task_svc.cancel_task(task.task_id, 1)
    assert cancelled.status == "cancelled"


async def test_task_cancel_from_running(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)
    await task_svc.start_task(task.task_id, 1)

    cancelled = await task_svc.cancel_task(task.task_id, 2)
    assert cancelled.status == "cancelled"


async def test_task_invalid_transition(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)
    await task_svc.start_task(task.task_id, 1)
    await task_svc.complete_task(task.task_id, 2)

    with pytest.raises(ValueError, match="Cannot start"):
        await task_svc.start_task(task.task_id, 3)


async def test_task_cancel_completed_fails(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)
    await task_svc.start_task(task.task_id, 1)
    await task_svc.complete_task(task.task_id, 2)

    with pytest.raises(ValueError, match="Cannot cancel"):
        await task_svc.cancel_task(task.task_id, 3)


async def test_task_not_found(task_svc: TaskService) -> None:
    with pytest.raises(ValueError, match="not found"):
        await task_svc.start_task("nonexistent", 1)


async def test_task_cas_conflict(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)

    with pytest.raises(CasConflict):
        await task_svc.start_task(task.task_id, 999)


async def test_task_pause_and_resume(task_svc: TaskService) -> None:
    task = _make_task()
    await task_svc.create_task(task)
    await task_svc.start_task(task.task_id, 1)

    now = _now()
    async with aiosqlite.connect(task_svc._db_path) as db:
        await db.execute(
            "UPDATE tasks SET status = 'paused', version = version + 1,"
            " updated_at = ? WHERE task_id = ?",
            (now, task.task_id),
        )
        await db.commit()

    resumed = await task_svc.start_task(task.task_id, 3)
    assert resumed.status == "running"


# ── TaskNode ──


async def test_create_and_get_node(node_svc: TaskNodeService) -> None:
    node = _make_node("task-1")
    await node_svc.create_node(node)

    fetched = await node_svc.get_node(node.node_id)
    assert fetched is not None
    assert fetched.task_id == "task-1"
    assert fetched.status == "pending"


async def test_list_nodes_by_task(node_svc: TaskNodeService) -> None:
    await node_svc.create_node(_make_node("task-1"))
    await node_svc.create_node(_make_node("task-1"))
    await node_svc.create_node(_make_node("task-2"))

    nodes = await node_svc.list_by_task("task-1")
    assert len(nodes) == 2


async def test_node_lifecycle(node_svc: TaskNodeService) -> None:
    node = _make_node("task-1")
    await node_svc.create_node(node)

    started = await node_svc.start_node(node.node_id, 1)
    assert started.status == "running"
    assert started.version == 2

    completed = await node_svc.complete_node(node.node_id, 2)
    assert completed.status == "completed"
    assert completed.version == 3


async def test_node_invalid_transition(node_svc: TaskNodeService) -> None:
    node = _make_node("task-1")
    await node_svc.create_node(node)
    await node_svc.start_node(node.node_id, 1)
    await node_svc.complete_node(node.node_id, 2)

    with pytest.raises(ValueError, match="Cannot start"):
        await node_svc.start_node(node.node_id, 3)


async def test_node_cas_conflict(node_svc: TaskNodeService) -> None:
    node = _make_node("task-1")
    await node_svc.create_node(node)

    with pytest.raises(CasConflict):
        await node_svc.start_node(node.node_id, 999)


async def test_node_not_found(node_svc: TaskNodeService) -> None:
    with pytest.raises(ValueError, match="not found"):
        await node_svc.start_node("nonexistent", 1)


# ── TaskRun ──


async def test_create_and_get_run(run_svc: TaskRunService) -> None:
    run = _make_run("node-1", "task-1")
    await run_svc.create_run(run)

    fetched = await run_svc.get_run(run.run_id)
    assert fetched is not None
    assert fetched.node_id == "node-1"
    assert fetched.status == "pending"


async def test_list_runs_by_node(run_svc: TaskRunService) -> None:
    await run_svc.create_run(_make_run("node-1", "task-1"))
    await run_svc.create_run(_make_run("node-1", "task-1"))
    await run_svc.create_run(_make_run("node-2", "task-1"))

    runs = await run_svc.list_by_node("node-1")
    assert len(runs) == 2


async def test_run_lifecycle(run_svc: TaskRunService) -> None:
    run = _make_run("node-1", "task-1")
    await run_svc.create_run(run)

    started = await run_svc.start_run(run.run_id, "be-1", "lease-1", 1)
    assert started.status == "running"
    assert started.backend_id == "be-1"
    assert started.lease_id == "lease-1"
    assert started.version == 2

    completed = await run_svc.complete_run(run.run_id, 2)
    assert completed.status == "completed"
    assert completed.version == 3


async def test_run_invalid_transition(run_svc: TaskRunService) -> None:
    run = _make_run("node-1", "task-1")
    await run_svc.create_run(run)
    await run_svc.start_run(run.run_id, "be-1", "lease-1", 1)
    await run_svc.complete_run(run.run_id, 2)

    with pytest.raises(ValueError, match="Cannot start"):
        await run_svc.start_run(run.run_id, "be-1", "lease-1", 3)


async def test_run_cas_conflict(run_svc: TaskRunService) -> None:
    run = _make_run("node-1", "task-1")
    await run_svc.create_run(run)

    with pytest.raises(CasConflict):
        await run_svc.start_run(run.run_id, "be-1", "lease-1", 999)


async def test_run_not_found(run_svc: TaskRunService) -> None:
    with pytest.raises(ValueError, match="not found"):
        await run_svc.start_run("nonexistent", "be-1", "lease-1", 1)


# ── TaskAssignment ──


async def test_create_and_list_assignment(
    task_svc: TaskService, assign_svc: TaskAssignmentService
) -> None:
    task = _make_task()
    await task_svc.create_task(task)

    assignment = TaskAssignment(
        assignment_id=f"asgn-{_uid()}",
        task_id=task.task_id,
        employee_id="emp-1",
        company_id="comp-1",
    )
    await assign_svc.create_assignment(assignment)

    by_task = await assign_svc.list_by_task(task.task_id)
    assert len(by_task) == 1
    assert by_task[0].employee_id == "emp-1"

    by_emp = await assign_svc.list_by_employee("emp-1")
    assert len(by_emp) == 1
