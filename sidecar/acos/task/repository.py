"""任务工作流仓储（P9-T1/T1a/T1b）。"""

from __future__ import annotations

import json
from typing import Optional

import aiosqlite

from acos.task.models import (
    TASK_TRANSITIONS,
    Checkpoint,
    PlanGeneration,
    Task,
    TaskAssignment,
    TaskNode,
)
from acos.workflows.service import CasConflict


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class TaskRepository:
    """tasks 表读写 + 状态机 CAS。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, task: Task) -> Task:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO tasks
                   (task_id, company_id, department_id, created_by_employee_id, title,
                    description, priority, status, manager_employee_id, manager_scope,
                    active_generation_id, assigned_backend_id, budget_currency,
                    budget_limit_micros, token_limit, goal, acceptance, inputs_json,
                    deadline_at, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id, task.company_id, task.department_id,
                    task.created_by_employee_id, task.title, task.description,
                    task.priority, task.status, task.manager_employee_id,
                    task.manager_scope, task.active_generation_id,
                    task.assigned_backend_id, task.budget_currency,
                    task.budget_limit_micros, task.token_limit, task.goal,
                    task.acceptance, task.inputs_json, task.deadline_at,
                    task.version, now, now,
                ),
            )
            await db.commit()
        return task

    async def get(self, task_id: str) -> Optional[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = await cur.fetchone()
            return self._row_to_task(row) if row else None

    async def list_by_company(self, company_id: str, status: Optional[str] = None) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cur = await db.execute(
                    "SELECT * FROM tasks WHERE company_id = ? AND status = ? ORDER BY created_at",
                    (company_id, status),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM tasks WHERE company_id = ? ORDER BY created_at",
                    (company_id,),
                )
            return [self._row_to_task(r) for r in await cur.fetchall()]

    async def list_by_managed_department_ids(self, department_ids: list[str]) -> list[Task]:
        if not department_ids:
            return []
        placeholders = ",".join("?" for _ in department_ids)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT * FROM tasks WHERE department_id IN ({placeholders})",
                department_ids,
            )
            return [self._row_to_task(r) for r in await cur.fetchall()]

    async def list_company_scope_tasks_for_root_leader(self, company_id: str) -> list[Task]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM tasks WHERE company_id = ? AND department_id IS NULL",
                (company_id,),
            )
            return [self._row_to_task(r) for r in await cur.fetchall()]

    async def set_active_generation(self, task_id: str, generation_id: str,
                                    expected_version: int) -> Task:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE tasks SET active_generation_id = ?, version = version + 1,
                       updated_at = ? WHERE task_id = ? AND version = ?""",
                (generation_id, now, task_id, expected_version),
            )
            if cur.rowcount == 0:
                raise CasConflict(f"Task {task_id} version mismatch")
            await db.commit()
        return await self.get(task_id)

    async def transition(self, task_id: str, expected_version: int, new_status: str) -> Task:
        task = await self.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if new_status not in TASK_TRANSITIONS.get(task.status, set()):
            raise ValueError(
                f"Cannot transition task {task.status} -> {new_status}"
            )
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE tasks SET status = ?, version = version + 1, updated_at = ?
                   WHERE task_id = ? AND version = ?""",
                (new_status, now, task_id, expected_version),
            )
            if cur.rowcount == 0:
                raise CasConflict(f"Task {task_id} version mismatch")
            await db.commit()
        return await self.get(task_id)

    @staticmethod
    def _row_to_task(row: aiosqlite.Row) -> Task:
        return Task(
            task_id=row["task_id"], company_id=row["company_id"], title=row["title"],
            status=row["status"], department_id=row["department_id"],
            created_by_employee_id=row["created_by_employee_id"],
            description=row["description"], priority=row["priority"],
            manager_employee_id=row["manager_employee_id"],
            manager_scope=row["manager_scope"],
            active_generation_id=row["active_generation_id"],
            assigned_backend_id=row["assigned_backend_id"],
            budget_currency=row["budget_currency"],
            budget_limit_micros=row["budget_limit_micros"],
            token_limit=row["token_limit"], goal=row["goal"],
            acceptance=row["acceptance"], inputs_json=row["inputs_json"],
            deadline_at=row["deadline_at"], version=row["version"],
        )


class TaskNodeRepository:
    """task_nodes 表读写 + 状态机 CAS。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, node: TaskNode) -> TaskNode:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO task_nodes
                   (node_id, task_id, company_id, node_type, status, assignee_employee_id,
                    generation_id, backend_id, depends_on, workspace_strategy,
                    outputs_schema, goal, max_concurrency, timeout_seconds, version,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    node.node_id, node.task_id, node.company_id, node.node_type,
                    node.status, node.assignee_employee_id, node.generation_id,
                    node.backend_id, json.dumps(node.depends_on),
                    node.workspace_strategy, node.outputs_schema, node.goal,
                    node.max_concurrency, node.timeout_seconds, now, now,
                ),
            )
            await db.commit()
        return node

    async def get(self, node_id: str) -> Optional[TaskNode]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM task_nodes WHERE node_id = ?", (node_id,))
            row = await cur.fetchone()
            return self._row_to_node(row) if row else None

    async def list_by_task(self, task_id: str) -> list[TaskNode]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM task_nodes WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            )
            return [self._row_to_node(r) for r in await cur.fetchall()]

    async def list_by_generation(self, generation_id: str) -> list[TaskNode]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM task_nodes WHERE generation_id = ? ORDER BY created_at",
                (generation_id,),
            )
            return [self._row_to_node(r) for r in await cur.fetchall()]

    async def delete_pending_for_task(self, task_id: str) -> int:
        """重新规划时清理尚未调度的 pending 草稿节点（避免 node_id 主键冲突）。"""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                "DELETE FROM task_nodes WHERE task_id = ? AND status = 'pending'",
                (task_id,),
            )
            n = cur.rowcount
            await db.commit()
            return n

    async def transition(self, node_id: str, expected_version: int, new_status: str) -> TaskNode:
        from acos.task.models import NODE_TRANSITIONS

        node = await self.get(node_id)
        if node is None:
            raise ValueError(f"Node {node_id} not found")
        if new_status not in NODE_TRANSITIONS.get(node.status, set()):
            raise ValueError(f"Cannot transition node {node.status} -> {new_status}")
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE task_nodes SET status = ?, version = version + 1, updated_at = ?
                   WHERE node_id = ? AND version = ?""",
                (new_status, now, node_id, expected_version),
            )
            if cur.rowcount == 0:
                raise CasConflict(f"Node {node_id} version mismatch")
            await db.commit()
        return await self.get(node_id)

    @staticmethod
    def _row_to_node(row: aiosqlite.Row) -> TaskNode:
        try:
            depends = json.loads(row["depends_on"]) if row["depends_on"] else []
        except (json.JSONDecodeError, TypeError):
            depends = []
        return TaskNode(
            node_id=row["node_id"], task_id=row["task_id"], company_id=row["company_id"],
            node_type=row["node_type"], status=row["status"],
            assignee_employee_id=row["assignee_employee_id"],
            generation_id=row["generation_id"], backend_id=row["backend_id"],
            depends_on=depends, workspace_strategy=row["workspace_strategy"],
            outputs_schema=row["outputs_schema"], goal=row["goal"],
            max_concurrency=row["max_concurrency"], timeout_seconds=row["timeout_seconds"],
            version=row["version"],
        )


class TaskAssignmentRepository:
    """task_assignments 表读写（P9-T1a）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, a: TaskAssignment) -> TaskAssignment:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO task_assignments
                   (assignment_id, task_id, node_id, employee_id, company_id,
                    generation_id, run_id, attempt, assignment_role,
                    department_id_at_assignment, granted_by, reason, active_from,
                    active_until, status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)""",
                (
                    a.assignment_id, a.task_id, a.node_id, a.employee_id, a.company_id,
                    a.generation_id or "", a.run_id, a.attempt, a.assignment_role,
                    a.department_id_at_assignment, a.granted_by, a.reason,
                    a.active_from or now, a.active_until, now, now,
                ),
            )
            await db.commit()
        return a

    async def list_by_task(self, task_id: str) -> list[TaskAssignment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM task_assignments WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            )
            return [self._row_to_assignment(r) for r in await cur.fetchall()]

    async def list_active_for_node(self, node_id: str, role: str) -> list[TaskAssignment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM task_assignments
                   WHERE node_id = ? AND assignment_role = ? AND status = 'active'""",
                (node_id, role),
            )
            return [self._row_to_assignment(r) for r in await cur.fetchall()]

    async def list_active_task_ids(self, employee_id: str) -> list[str]:
        """供 P4-T3 compute_scope 调用：只返回 active 记录对应 task_id（去重）。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT DISTINCT task_id FROM task_assignments
                   WHERE employee_id = ? AND status = 'active'""",
                (employee_id,),
            )
            return [r["task_id"] for r in await cur.fetchall()]

    async def close(self, assignment_id: str, expected_version: int) -> TaskAssignment:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE task_assignments
                   SET status = 'closed', active_until = ?, version = version + 1,
                       updated_at = ?
                   WHERE assignment_id = ? AND version = ? AND status = 'active'""",
                (now, now, assignment_id, expected_version),
            )
            if cur.rowcount == 0:
                raise CasConflict(f"Assignment {assignment_id} version mismatch")
            await db.commit()
        return await self.get(assignment_id)

    async def get(self, assignment_id: str) -> Optional[TaskAssignment]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM task_assignments WHERE assignment_id = ?", (assignment_id,)
            )
            row = await cur.fetchone()
            return self._row_to_assignment(row) if row else None

    @staticmethod
    def _row_to_assignment(row: aiosqlite.Row) -> TaskAssignment:
        return TaskAssignment(
            assignment_id=row["assignment_id"], task_id=row["task_id"],
            employee_id=row["employee_id"], company_id=row["company_id"],
            node_id=row["node_id"], generation_id=row["generation_id"],
            run_id=row["run_id"], attempt=row["attempt"],
            assignment_role=row["assignment_role"],
            department_id_at_assignment=row["department_id_at_assignment"],
            granted_by=row["granted_by"], reason=row["reason"],
            active_from=row["active_from"], active_until=row["active_until"],
            status=row["status"], version=row["version"],
        )


class PlanGenerationRepository:
    """plan_generations 表读写（P9-T3）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, g: PlanGeneration) -> PlanGeneration:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO plan_generations
                   (generation_id, task_id, company_id, generation_no, status, plan_hash,
                    dag_json, risk_summary, created_by_employee_id, parent_generation_id,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    g.generation_id, g.task_id, g.company_id, g.generation_no, g.status,
                    g.plan_hash, g.dag_json, g.risk_summary, g.created_by_employee_id,
                    g.parent_generation_id, now, now,
                ),
            )
            await db.commit()
        return g

    async def get(self, generation_id: str) -> Optional[PlanGeneration]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM plan_generations WHERE generation_id = ?", (generation_id,)
            )
            row = await cur.fetchone()
            return self._row_to_gen(row) if row else None

    async def list_by_task(self, task_id: str) -> list[PlanGeneration]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM plan_generations WHERE task_id = ? ORDER BY generation_no",
                (task_id,),
            )
            return [self._row_to_gen(r) for r in await cur.fetchall()]

    async def get_active(self, task_id: str) -> Optional[PlanGeneration]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM plan_generations WHERE task_id = ? AND status = 'active'",
                (task_id,),
            )
            row = await cur.fetchone()
            return self._row_to_gen(row) if row else None

    async def transition(
        self, generation_id: str, expected_version: int, new_status: str,
    ) -> PlanGeneration:
        from acos.task.models import GENERATION_TRANSITIONS

        g = await self.get(generation_id)
        if g is None:
            raise ValueError(f"Generation {generation_id} not found")
        if new_status not in GENERATION_TRANSITIONS.get(g.status, set()):
            raise ValueError(f"Cannot transition generation {g.status} -> {new_status}")
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE plan_generations SET status = ?, version = version + 1, updated_at = ?
                   WHERE generation_id = ? AND version = ?""",
                (new_status, now, generation_id, expected_version),
            )
            if cur.rowcount == 0:
                raise CasConflict(f"Generation {generation_id} version mismatch")
            await db.commit()
        return await self.get(generation_id)

    @staticmethod
    def _row_to_gen(row: aiosqlite.Row) -> PlanGeneration:
        return PlanGeneration(
            generation_id=row["generation_id"], task_id=row["task_id"],
            company_id=row["company_id"], plan_hash=row["plan_hash"],
            generation_no=row["generation_no"], status=row["status"],
            dag_json=row["dag_json"], risk_summary=row["risk_summary"],
            created_by_employee_id=row["created_by_employee_id"],
            parent_generation_id=row["parent_generation_id"], version=row["version"],
        )


class CheckpointRepository:
    """checkpoints 表读写（P9-T8）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, c: Checkpoint) -> Checkpoint:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO checkpoints
                   (checkpoint_id, company_id, task_id, task_cursor, plan_hash,
                    context_hash, generation_id, run_id, event_offset, executor_state,
                    checksum, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    c.checkpoint_id, c.company_id, c.task_id, c.task_cursor, c.plan_hash,
                    c.context_hash, c.generation_id, c.run_id, c.event_offset,
                    c.executor_state, c.checksum,
                ),
            )
            await db.commit()
        return c

    async def list_by_task_desc(self, task_id: str, limit: int = 50,
                                cursor: Optional[str] = None) -> tuple[list[Checkpoint], bool]:
        """按 (created_at DESC, checkpoint_id DESC) 分页，不返回 executor_state。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = "SELECT * FROM checkpoints WHERE task_id = ?"
            args: list = [task_id]
            if cursor:
                sql += (
                    " AND (created_at, checkpoint_id) < "
                    "(SELECT created_at, checkpoint_id FROM checkpoints "
                    "WHERE checkpoint_id = ?)"
                )
                args.append(cursor)
            sql += " ORDER BY created_at DESC, checkpoint_id DESC LIMIT ?"
            args.append(limit + 1)
            cur = await db.execute(sql, args)
            rows = await cur.fetchall()
            has_more = len(rows) > limit
            rows = rows[:limit]
            return [self._row_to_cp(r) for r in rows], has_more

    @staticmethod
    def _row_to_cp(row: aiosqlite.Row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"], company_id=row["company_id"],
            task_id=row["task_id"], task_cursor=row["task_cursor"],
            checksum=row["checksum"], plan_hash=row["plan_hash"],
            context_hash=row["context_hash"], generation_id=row["generation_id"],
            run_id=row["run_id"], event_offset=row["event_offset"],
            executor_state=row["executor_state"],
        )
