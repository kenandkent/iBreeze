"""权限引擎 - 计算授权范围与资源鉴权。

实现设计 §8.1–§8.4 的结构化 AuthorizedScope 与具体资源鉴权。
compute_scope 为纯函数（无副作用、不写审计）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import aiosqlite

from acos.rpc.errors import ORG_PERM_DENIED, create_error


class PermissionEngine:
    """权限引擎。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ── 内部查询辅助 ──────────────────────────────────────

    async def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def _all_department_ids(self, db, company_id: str) -> list[str]:
        cur = await db.execute(
            "SELECT department_id FROM departments WHERE company_id = ? AND deleted_at IS NULL",
            (company_id,),
        )
        return [r["department_id"] for r in await cur.fetchall()]

    async def _descendant_department_ids(
        self, db, company_id: str, department_id: str, include_self: bool = True
    ) -> list[str]:
        if include_self:
            cur = await db.execute(
                """SELECT descendant_department_id FROM department_closure
                   WHERE company_id = ? AND ancestor_department_id = ?""",
                (company_id, department_id),
            )
        else:
            cur = await db.execute(
                """SELECT descendant_department_id FROM department_closure
                   WHERE company_id = ? AND ancestor_department_id = ? AND depth > 0""",
                (company_id, department_id),
            )
        return [r["descendant_department_id"] for r in await cur.fetchall()]

    async def _employee_department(self, db, employee_id: str) -> str | None:
        cur = await db.execute(
            "SELECT department_id, company_id FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
            (employee_id,),
        )
        row = await cur.fetchone()
        return row["department_id"] if row else None

    async def _led_department_ids(self, db, company_id: str, employee_id: str) -> list[str]:
        """返回该职员作为 leader_employee_id 的部门及其后代（managed_department_ids）。"""
        cur = await db.execute(
            "SELECT department_id FROM departments WHERE leader_employee_id = ? AND company_id = ? AND deleted_at IS NULL",
            (employee_id, company_id),
        )
        led = [r["department_id"] for r in await cur.fetchall()]
        result: list[str] = []
        for d in led:
            result.extend(await self._descendant_department_ids(db, company_id, d, include_self=True))
        # 去重保序
        seen: set[str] = set()
        unique = []
        for d in result:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    async def _managed_employee_ids(self, db, company_id: str, managed_department_ids: list[str]) -> list[str]:
        """部门闭包：本人是部门负责人的所有部门（含后代）里的全部职员。"""
        if not managed_department_ids:
            return []
        placeholders = ",".join("?" for _ in managed_department_ids)
        cur = await db.execute(
            f"""SELECT employee_id FROM employees
                WHERE company_id = ? AND deleted_at IS NULL
                  AND department_id IN ({placeholders})""",
            (company_id, *managed_department_ids),
        )
        return [r["employee_id"] for r in await cur.fetchall()]

    async def _reporting_subordinate_ids(self, db, employee_id: str) -> list[str]:
        """从 employee_reporting_closure 表查询所有下属（含间接，不含自身）。"""
        cur = await db.execute(
            """SELECT descendant_employee_id FROM employee_reporting_closure
               WHERE ancestor_employee_id = ? AND depth > 0
               ORDER BY depth""",
            (employee_id,),
        )
        return [r["descendant_employee_id"] for r in await cur.fetchall()]

    async def _active_grants(
        self, db, employee_id: str, company_id: str
    ) -> tuple[list[str], list[str]]:
        now = await self._now_iso()
        cur = await db.execute(
            """SELECT target_type, target_id, permission FROM access_grants
               WHERE employee_id = ? AND company_id = ?
                 AND status = 'active' AND expires_at > ?""",
            (employee_id, company_id, now),
        )
        rows = await cur.fetchall()
        granted_departments: list[str] = []
        granted_tasks: list[str] = []
        for row in rows:
            if row["target_type"] == "department" and row["permission"] == "department_read":
                granted_departments.append(row["target_id"])
            elif row["target_type"] == "task" and row["permission"] == "task_read":
                granted_tasks.append(row["target_id"])
        return sorted(set(granted_departments)), sorted(set(granted_tasks))

    async def _visible_task_ids(
        self, db, company_id: str, employee_id: str,
        managed_department_ids: list[str], granted_tasks: list[str],
        is_root_leader: bool,
    ) -> list[str]:
        task_ids: set[str] = set()
        # 本人活动 assignment
        cur = await db.execute(
            """SELECT task_id FROM task_assignments
               WHERE employee_id = ? AND company_id = ? AND status = 'active'""",
            (employee_id, company_id),
        )
        for r in await cur.fetchall():
            task_ids.add(r["task_id"])
        # managed department 内任务
        if managed_department_ids:
            placeholders = ",".join("?" for _ in managed_department_ids)
            cur = await db.execute(
                f"""SELECT task_id FROM tasks
                    WHERE company_id = ? AND department_id IN ({placeholders})""",
                (company_id, *managed_department_ids),
            )
            for r in await cur.fetchall():
                task_ids.add(r["task_id"])
        # 公司负责人可见的 company-scope 任务
        if is_root_leader:
            cur = await db.execute(
                """SELECT task_id FROM tasks
                   WHERE company_id = ? AND department_id IS NULL""",
                (company_id,),
            )
            for r in await cur.fetchall():
                task_ids.add(r["task_id"])
        # 有效 task grant
        for t in granted_tasks:
            task_ids.add(t)
        return sorted(task_ids)

    # ── compute_scope ─────────────────────────────────────

    async def compute_scope(
        self, employee_id: str, company_id: str, task_id: str | None = None
    ) -> dict:
        """计算结构化授权范围（纯函数）。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            emp_dept = await self._employee_department(db, employee_id)
            is_company_leader = False
            if emp_dept is not None:
                cur = await db.execute(
                    """SELECT 1 FROM employees
                       WHERE employee_id = ? AND company_id = ? AND deleted_at IS NULL
                         AND employee_type = 'company_leader'""",
                    (employee_id, company_id),
                )
                is_company_leader = (await cur.fetchone()) is not None

            # 管理的部门
            managed_department_ids = await self._led_department_ids(db, company_id, employee_id)

            # 可见部门（设计 §8.2）
            if is_company_leader:
                visible_department_ids = await self._all_department_ids(db, company_id)
            elif emp_dept is not None:
                if managed_department_ids:
                    # 部门负责人：本人领导的部门及后代
                    vis: set[str] = set()
                    for d in managed_department_ids:
                        vis.update(await self._descendant_department_ids(db, company_id, d, include_self=True))
                    visible_department_ids = sorted(vis)
                else:
                    # 普通职员：仅本人部门，不含后代
                    visible_department_ids = [emp_dept]
            else:
                visible_department_ids = []

            # 私有可见职员
            managed_employee_ids = await self._managed_employee_ids(
                db, company_id, managed_department_ids
            )
            reporting_subordinate_ids = await self._reporting_subordinate_ids(db, employee_id)
            private_visible_employee_ids = sorted(
                set(managed_employee_ids) | set(reporting_subordinate_ids)
            )

            # 授权（临时跨部门）
            granted_departments, granted_tasks = await self._active_grants(
                db, employee_id, company_id
            )
            visible_department_ids = sorted(set(visible_department_ids) | set(granted_departments))

            # 可见任务
            visible_task_ids = await self._visible_task_ids(
                db, company_id, employee_id, managed_department_ids,
                granted_tasks, is_company_leader,
            )

        scope: dict = {
            "company_id": company_id,
            "employee_id": employee_id,
            "visible_department_ids": visible_department_ids,
            "managed_department_ids": managed_department_ids,
            "visible_task_ids": visible_task_ids,
            "private_visible_employee_ids": private_visible_employee_ids,
            "granted_departments": granted_departments,
            "granted_tasks": granted_tasks,
        }
        scope_bytes = json.dumps(scope, sort_keys=True).encode()
        scope["scope_hash"] = hashlib.sha256(scope_bytes).hexdigest()
        return scope

    # ── authorize ─────────────────────────────────────────

    async def authorize(
        self,
        employee_id: str,
        company_id: str,
        resource_type: str,
        resource_id: str,
        action: str = "read",
        task_id: str | None = None,
    ) -> dict:
        """具体资源鉴权，并写 acl_audit_log。"""
        scope = await self.compute_scope(employee_id, company_id, task_id)
        decision = "deny"
        matched_rule = "default_deny"

        if resource_type == "department":
            if resource_id in scope["visible_department_ids"]:
                decision = "allow"
                matched_rule = "inherited_department"
            elif resource_id in scope["granted_departments"]:
                decision = "allow"
                matched_rule = "grant_department"
        elif resource_type == "employee":
            if resource_id == employee_id:
                decision = "allow"
                matched_rule = "own_employee"
            elif resource_id in scope["private_visible_employee_ids"]:
                decision = "allow"
                matched_rule = "inherited_employee"
        elif resource_type == "task":
            if resource_id in scope["visible_task_ids"]:
                decision = "allow"
                matched_rule = "inherited_task"
            elif resource_id in scope["granted_tasks"]:
                decision = "allow"
                matched_rule = "grant_task"
        elif resource_type in ("knowledge", "document"):
            # company 级可见性：同公司即允许（v1 最小实现）
            decision = "allow"
            matched_rule = "company_visibility"
        else:
            matched_rule = "unknown_resource_type"

        # 写审计日志
        trace_id = resource_id
        await self._write_audit_log(
            company_id, employee_id, resource_type, resource_id,
            action, decision, matched_rule, trace_id,
        )
        return {"decision": decision, "matched_rule": matched_rule}

    async def _write_audit_log(
        self, company_id, employee_id, resource_type, resource_id,
        action, decision, matched_rule, trace_id,
    ) -> None:
        import uuid

        now = await self._now_iso()
        try:
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    """INSERT INTO acl_audit_log
                       (id, subject, company_id, resource_type, resource_id,
                        action, decision, matched_rule, trace_id, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (str(uuid.uuid4()), employee_id, company_id, resource_type,
                     resource_id, action, decision, matched_rule, trace_id, now),
                )
                await db.commit()
        except aiosqlite.OperationalError:
            # 表不存在时静默跳过（迁移未应用时由调用方负责）
            pass

    # ── grant / revoke ────────────────────────────────────

    async def grant(
        self,
        company_id: str,
        employee_id: str,
        target_type: str,
        target_id: str,
        permission: str,
        expires_at: str,
        approved_by: str,
    ) -> str:
        """授予访问权限，返回 grant_id。"""
        import uuid

        grant_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO access_grants
                   (grant_id, company_id, employee_id, target_type, target_id,
                    permission, status, expires_at, approved_by, version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, 1, ?)""",
                (grant_id, company_id, employee_id, target_type, target_id,
                 permission, expires_at, approved_by, now),
            )
            await db.commit()
        return grant_id

    async def revoke(self, grant_id: str, company_id: str, expected_version: int) -> bool:
        """撤销授权。"""
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """UPDATE access_grants
                   SET status = 'revoked', version = version + 1, revoked_at = ?
                   WHERE grant_id = ? AND company_id = ? AND version = ? AND status = 'active'""",
                (now, grant_id, company_id, expected_version),
            )
            await db.commit()
            return cursor.rowcount == 1
