"""任务生命周期 RPC 方法集合。"""

from __future__ import annotations

import json as _json
from typing import Any

import aiosqlite

from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer
from acos.task.service import TaskService
from acos.workflows.service import CasConflict


class TaskMethods:
    """任务相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._svc = TaskService(db_path)

    def register_to(self, server: RPCServer) -> None:
        server.register_method("task.list", self._task_list)
        server.register_method("task.start", self._task_start)
        server.register_method("task.complete", self._task_complete)
        server.register_method("task.cancel", self._task_cancel)
        server.register_method("task.retrySubtask", self._task_retry_subtask)
        server.register_method("task.create", self._task_create)
        server.register_method("task.nodes", self._task_nodes)

    async def _task_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if company_id:
                cur = await db.execute(
                    "SELECT task_id, company_id, title, description, status, priority, version, created_at "
                    "FROM tasks WHERE company_id = ? ORDER BY created_at DESC",
                    (company_id,),
                )
            else:
                cur = await db.execute(
                    "SELECT task_id, company_id, title, description, status, priority, version, created_at "
                    "FROM tasks ORDER BY created_at DESC",
                )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def _task_start(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        expected_version = params.get("expected_version")
        if not task_id or expected_version is None:
            return {"error": "missing task_id or expected_version"}
        try:
            task = await self._svc.start_task(task_id, expected_version)
            return {"task_id": task.task_id, "version": task.version, "status": task.status}
        except CasConflict:
            return {"error": "version conflict"}
        except AcosError as e:
            return {"error": e.code, "message": e.message}
        except ValueError as e:
            return {"error": str(e)}

    async def _task_complete(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        expected_version = params.get("expected_version")
        if not task_id or expected_version is None:
            return {"error": "missing task_id or expected_version"}
        try:
            task = await self._svc.complete_task(task_id, expected_version)
            return {"task_id": task.task_id, "version": task.version, "status": task.status}
        except CasConflict:
            return {"error": "version conflict"}
        except AcosError as e:
            return {"error": e.code, "message": e.message}
        except ValueError as e:
            return {"error": str(e)}

    async def _task_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        expected_version = params.get("expected_version")
        if not task_id or expected_version is None:
            return {"error": "missing task_id or expected_version"}
        try:
            res = await self._svc.cancel_task(task_id, expected_version)
            return {"task_id": res["task_id"], "status": res["status"]}
        except CasConflict:
            return {"error": "version conflict"}
        except AcosError as e:
            return {"error": e.code, "message": e.message}
        except ValueError as e:
            return {"error": str(e)}

    async def _task_retry_subtask(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("task_id")
        node_id = params.get("node_id")
        reason = params.get("reason", "")
        if not task_id or not node_id:
            return {"error": "missing task_id or node_id"}
        try:
            result = await self._svc.retry_subtask(task_id, node_id, reason)
            return result
        except AcosError as e:
            return {"error": e.code, "message": e.message}
        except ValueError as e:
            return {"error": str(e)}

    async def _task_create(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        title = params.get("title", "")
        manager_employee_id = params.get("manager_employee_id", "system")
        manager_scope = params.get("manager_scope", "dept")
        goal = params.get("goal", "")
        acceptance = params.get("acceptance", "")
        if not company_id or not title:
            return {"error": "missing company_id or title"}
        try:
            result = await self._svc.create_task(
                company_id=company_id,
                title=title,
                manager_employee_id=manager_employee_id,
                manager_scope=manager_scope,
                goal=goal,
                acceptance=acceptance,
                department_id=params.get("department_id"),
                backend_id=params.get("backend_id"),
                budget=params.get("budget"),
                created_by=params.get("created_by", "system"),
                priority=params.get("priority", 5),
                inputs=params.get("inputs"),
            )
            return result
        except AcosError as e:
            return {"error": e.code, "message": e.message}
        except ValueError as e:
            return {"error": str(e)}

    async def _task_nodes(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """task.nodes：返回任务的 DAG 节点列表（含依赖关系，供前端可视化）。"""
        task_id = params.get("task_id")
        if not task_id:
            return []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT node_id, node_type, goal, status, depends_on,
                          assignee_employee_id, generation_id, version
                   FROM task_nodes WHERE task_id = ? ORDER BY created_at""",
                (task_id,),
            )
            rows = await cur.fetchall()
            result = []
            for r in rows:
                deps = r["depends_on"]
                if isinstance(deps, str):
                    try:
                        deps = _json.loads(deps)
                    except Exception:
                        deps = []
                result.append({
                    "node_id": r["node_id"],
                    "node_type": r["node_type"],
                    "goal": r["goal"],
                    "status": r["status"],
                    "depends_on": deps or [],
                    "assignee_employee_id": r["assignee_employee_id"],
                    "generation_id": r["generation_id"],
                    "version": r["version"],
                })
            return result
