"""任务工作流服务：Task、TaskNode、TaskRun 的 CRUD 与状态机。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.workflows.models import Task, TaskAssignment, TaskNode, TaskRun

# ── 状态机 ──

TASK_TRANSITIONS: dict[str, set[str]] = {
    "created": {"planning", "running", "cancelled"},
    "planning": {"running", "cancelled"},
    "running": {"paused", "completed", "failed", "cancelled"},
    "paused": {"running", "cancelled"},
}

NODE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running"},
    "running": {"completed", "failed"},
}

RUN_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running"},
    "running": {"completed", "failed"},
}


class CasConflict(Exception):
    """CAS 版本冲突。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_task(row: aiosqlite.Row) -> Task:
    return Task(
        task_id=row["task_id"],
        company_id=row["company_id"],
        department_id=row["department_id"],
        created_by_employee_id=row["created_by_employee_id"],
        title=row["title"],
        description=row["description"],
        priority=row["priority"],
        status=row["status"],
        assigned_backend_id=row["assigned_backend_id"],
        assigned_capability_id=row["assigned_capability_id"],
        assigned_capability_version=row["assigned_capability_version"],
        assigned_capability_checksum=row["assigned_capability_checksum"],
        deadline_at=row["deadline_at"],
        version=row["version"],
    )


def _row_to_node(row: aiosqlite.Row) -> TaskNode:
    return TaskNode(
        node_id=row["node_id"],
        task_id=row["task_id"],
        company_id=row["company_id"],
        node_type=row["node_type"],
        status=row["status"],
        assignee_employee_id=row["assignee_employee_id"],
        max_concurrency=row["max_concurrency"],
        timeout_seconds=row["timeout_seconds"],
        version=row["version"],
    )


def _row_to_run(row: aiosqlite.Row) -> TaskRun:
    return TaskRun(
        run_id=row["run_id"],
        node_id=row["node_id"],
        task_id=row["task_id"],
        company_id=row["company_id"],
        backend_id=row["backend_id"],
        lease_id=row["lease_id"],
        status=row["status"],
        capability_checksum=row["capability_checksum"],
        version=row["version"],
    )


class TaskService:
    """Task CRUD 与状态流转。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create_task(self, task: Task) -> Task:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO tasks
                   (task_id, company_id, department_id, created_by_employee_id,
                    title, description, priority, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    task.task_id,
                    task.company_id,
                    task.department_id,
                    task.created_by_employee_id,
                    task.title,
                    task.description,
                    task.priority,
                    task.status,
                    now,
                    now,
                ),
            )
            await db.commit()
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_task(row)

    async def list_tasks(
        self, company_id: str, status: Optional[str] = None
    ) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status is not None:
                cursor = await db.execute(
                    "SELECT * FROM tasks WHERE company_id = ? AND status = ? ORDER BY created_at",
                    (company_id, status),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM tasks WHERE company_id = ? ORDER BY created_at",
                    (company_id,),
                )
            rows = await cursor.fetchall()
            return [_row_to_task(r) for r in rows]

    async def _transition_task(
        self, task_id: str, expected_version: int, new_status: str
    ) -> Task:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE tasks
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE task_id = ? AND version = ?""",
                (new_status, now, task_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise CasConflict(
                    f"Task {task_id} version mismatch: expected {expected_version}"
                )
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
            )
            return _row_to_task(await cursor.fetchone())

    async def start_task(self, task_id: str, expected_version: int) -> Task:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        allowed = TASK_TRANSITIONS.get(task.status, set())
        if "running" not in allowed:
            raise ValueError(
                f"Cannot start task in status '{task.status}'; allowed: {allowed}"
            )
        return await self._transition_task(task_id, expected_version, "running")

    async def complete_task(self, task_id: str, expected_version: int) -> Task:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        allowed = TASK_TRANSITIONS.get(task.status, set())
        if "completed" not in allowed:
            raise ValueError(
                f"Cannot complete task in status '{task.status}'; allowed: {allowed}"
            )
        return await self._transition_task(task_id, expected_version, "completed")

    async def cancel_task(self, task_id: str, expected_version: int) -> Task:
        task = await self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        allowed = TASK_TRANSITIONS.get(task.status, set())
        if "cancelled" not in allowed:
            raise ValueError(
                f"Cannot cancel task in status '{task.status}'; allowed: {allowed}"
            )
        return await self._transition_task(task_id, expected_version, "cancelled")


class TaskNodeService:
    """TaskNode CRUD 与状态流转。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create_node(self, node: TaskNode) -> TaskNode:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO task_nodes
                   (node_id, task_id, company_id, node_type, status,
                    assignee_employee_id, max_concurrency, timeout_seconds,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    node.node_id,
                    node.task_id,
                    node.company_id,
                    node.node_type,
                    node.status,
                    node.assignee_employee_id,
                    node.max_concurrency,
                    node.timeout_seconds,
                    now,
                    now,
                ),
            )
            await db.commit()
        return node

    async def get_node(self, node_id: str) -> Optional[TaskNode]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_nodes WHERE node_id = ?", (node_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_node(row)

    async def list_by_task(self, task_id: str) -> list[TaskNode]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_nodes WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            )
            rows = await cursor.fetchall()
            return [_row_to_node(r) for r in rows]

    async def _transition_node(
        self, node_id: str, expected_version: int, new_status: str
    ) -> TaskNode:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE task_nodes
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE node_id = ? AND version = ?""",
                (new_status, now, node_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise CasConflict(
                    f"TaskNode {node_id} version mismatch: expected {expected_version}"
                )
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM task_nodes WHERE node_id = ?", (node_id,)
            )
            return _row_to_node(await cursor.fetchone())

    async def start_node(self, node_id: str, expected_version: int) -> TaskNode:
        node = await self.get_node(node_id)
        if node is None:
            raise ValueError(f"TaskNode {node_id} not found")
        allowed = NODE_TRANSITIONS.get(node.status, set())
        if "running" not in allowed:
            raise ValueError(
                f"Cannot start node in status '{node.status}'; allowed: {allowed}"
            )
        return await self._transition_node(node_id, expected_version, "running")

    async def complete_node(self, node_id: str, expected_version: int) -> TaskNode:
        node = await self.get_node(node_id)
        if node is None:
            raise ValueError(f"TaskNode {node_id} not found")
        allowed = NODE_TRANSITIONS.get(node.status, set())
        if "completed" not in allowed:
            raise ValueError(
                f"Cannot complete node in status '{node.status}'; allowed: {allowed}"
            )
        return await self._transition_node(node_id, expected_version, "completed")


class TaskRunService:
    """TaskRun CRUD 与状态流转。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create_run(self, run: TaskRun) -> TaskRun:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO task_runs
                   (run_id, node_id, task_id, company_id, backend_id, lease_id,
                    status, capability_checksum, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    run.run_id,
                    run.node_id,
                    run.task_id,
                    run.company_id,
                    run.backend_id,
                    run.lease_id,
                    run.status,
                    run.capability_checksum,
                    now,
                    now,
                ),
            )
            await db.commit()
        return run

    async def get_run(self, run_id: str) -> Optional[TaskRun]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_runs WHERE run_id = ?", (run_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_run(row)

    async def list_by_node(self, node_id: str) -> list[TaskRun]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_runs WHERE node_id = ? ORDER BY created_at",
                (node_id,),
            )
            rows = await cursor.fetchall()
            return [_row_to_run(r) for r in rows]

    async def _transition_run(
        self, run_id: str, expected_version: int, new_status: str
    ) -> TaskRun:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE task_runs
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE run_id = ? AND version = ?""",
                (new_status, now, run_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise CasConflict(
                    f"TaskRun {run_id} version mismatch: expected {expected_version}"
                )
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM task_runs WHERE run_id = ?", (run_id,)
            )
            return _row_to_run(await cursor.fetchone())

    async def start_run(
        self,
        run_id: str,
        backend_id: str,
        lease_id: str,
        expected_version: int,
    ) -> TaskRun:
        run = await self.get_run(run_id)
        if run is None:
            raise ValueError(f"TaskRun {run_id} not found")
        allowed = RUN_TRANSITIONS.get(run.status, set())
        if "running" not in allowed:
            raise ValueError(
                f"Cannot start run in status '{run.status}'; allowed: {allowed}"
            )
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE task_runs
                   SET status = 'running', backend_id = ?, lease_id = ?,
                       version = version + 1, updated_at = ?
                   WHERE run_id = ? AND version = ?""",
                (backend_id, lease_id, now, run_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise CasConflict(
                    f"TaskRun {run_id} version mismatch: expected {expected_version}"
                )
            await db.commit()
            cursor = await db.execute(
                "SELECT * FROM task_runs WHERE run_id = ?", (run_id,)
            )
            return _row_to_run(await cursor.fetchone())

    async def complete_run(self, run_id: str, expected_version: int) -> TaskRun:
        run = await self.get_run(run_id)
        if run is None:
            raise ValueError(f"TaskRun {run_id} not found")
        allowed = RUN_TRANSITIONS.get(run.status, set())
        if "completed" not in allowed:
            raise ValueError(
                f"Cannot complete run in status '{run.status}'; allowed: {allowed}"
            )
        return await self._transition_run(run_id, expected_version, "completed")


class TaskAssignmentService:
    """TaskAssignment CRUD。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create_assignment(self, assignment: TaskAssignment) -> TaskAssignment:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO task_assignments
                   (assignment_id, task_id, node_id, employee_id, company_id,
                    role, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    assignment.assignment_id,
                    assignment.task_id,
                    assignment.node_id,
                    assignment.employee_id,
                    assignment.company_id,
                    assignment.role,
                    assignment.status,
                    now,
                ),
            )
            await db.commit()
        return assignment

    async def list_by_task(self, task_id: str) -> list[TaskAssignment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_assignments WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            )
            rows = await cursor.fetchall()
            return [
                TaskAssignment(
                    assignment_id=r["assignment_id"],
                    task_id=r["task_id"],
                    node_id=r["node_id"],
                    employee_id=r["employee_id"],
                    company_id=r["company_id"],
                    role=r["role"],
                    status=r["status"],
                )
                for r in rows
            ]

    async def list_by_employee(self, employee_id: str) -> list[TaskAssignment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM task_assignments WHERE employee_id = ? ORDER BY created_at",
                (employee_id,),
            )
            rows = await cursor.fetchall()
            return [
                TaskAssignment(
                    assignment_id=r["assignment_id"],
                    task_id=r["task_id"],
                    node_id=r["node_id"],
                    employee_id=r["employee_id"],
                    company_id=r["company_id"],
                    role=r["role"],
                    status=r["status"],
                )
                for r in rows
            ]
