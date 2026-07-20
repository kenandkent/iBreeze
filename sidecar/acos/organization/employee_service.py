"""员工服务。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.organization.models import Employee
from acos.organization.reporting_closure import ReportingClosure
from acos.rpc.errors import (
    ORG_NOT_FOUND,
    ORG_REPORTING_CYCLE,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)

VALID_EMPLOYEE_STATUSES = frozenset({"created", "active", "suspended", "archived", "deleted"})

# 状态转换规则
_EMPLOYEE_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"active"}),
    "active": frozenset({"suspended", "archived"}),
    "suspended": frozenset({"active", "archived"}),
    "archived": frozenset({"deleted"}),
}


class EmployeeService:
    """员工服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_employee(row: aiosqlite.Row) -> Employee:
        return Employee(
            employee_id=row["employee_id"],
            company_id=row["company_id"],
            department_id=row["department_id"],
            template_id=row["template_id"],
            capability_snapshot=json.loads(row["capability_snapshot"]),
            name=row["name"],
            role_name=row["role_name"],
            employee_type=row["employee_type"],
            reports_to_employee_id=row["reports_to_employee_id"],
            stability_level=row["stability_level"],
            status=row["status"],
            session_transfer_state=row["session_transfer_state"],
            primary_session_thread_id=row["primary_session_thread_id"],
            version=row["version"],
        )

    async def create(
        self,
        company_id: str,
        department_id: str,
        template_id: str,
        name: str,
        capability_snapshot: dict | None = None,
        role_name: str = "",
        employee_type: str = "employee",
    ) -> Employee:
        """从模板创建员工。"""
        now = self._now()
        employee = Employee(
            company_id=company_id,
            department_id=department_id,
            template_id=template_id,
            capability_snapshot=capability_snapshot or {},
            name=name,
            role_name=role_name,
            employee_type=employee_type,
            status="created",
        )

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO employees
                   (employee_id, company_id, department_id, template_id,
                    capability_snapshot, name, role_name, employee_type,
                    reports_to_employee_id, stability_level, status,
                    session_transfer_state, primary_session_thread_id,
                    version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 5, 'created',
                           'none', NULL, 1, ?, ?)""",
                (
                    employee.employee_id, employee.company_id, employee.department_id,
                    employee.template_id, json.dumps(employee.capability_snapshot),
                    employee.name, employee.role_name, employee.employee_type,
                    now, now,
                ),
            )
            # 维护汇报链闭包表：新员工自引用
            rc = ReportingClosure()
            await rc.add_employee(db, company_id, employee.employee_id, None)
            await db.commit()
        return employee

    async def _transition(
        self,
        employee_id: str,
        company_id: str,
        expected_version: int,
        target_status: str,
    ) -> Employee:
        """通用状态转换。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND company_id = ?",
                (employee_id, company_id),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"员工 {employee_id} 不存在")

            current_status = current["status"]
            allowed = _EMPLOYEE_TRANSITIONS.get(current_status, frozenset())
            if target_status not in allowed:
                raise create_error(
                    ORG_STATE_INVALID,
                    f"不允许从 {current_status} 转换到 {target_status}",
                )

            cursor = await db.execute(
                """UPDATE employees
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE employee_id = ? AND company_id = ? AND version = ?""",
                (target_status, now, employee_id, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: employee {employee_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ?", (employee_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_employee(row)

    async def activate(self, employee_id: str, company_id: str, expected_version: int) -> Employee:
        """激活员工。"""
        return await self._transition(employee_id, company_id, expected_version, "active")

    async def suspend(self, employee_id: str, company_id: str, expected_version: int) -> Employee:
        """挂起员工。"""
        return await self._transition(employee_id, company_id, expected_version, "suspended")

    async def resume(self, employee_id: str, company_id: str, expected_version: int) -> Employee:
        """恢复员工。"""
        return await self._transition(employee_id, company_id, expected_version, "active")

    async def archive(self, employee_id: str, company_id: str, expected_version: int) -> Employee:
        """归档员工。"""
        return await self._transition(employee_id, company_id, expected_version, "archived")

    async def delete(self, employee_id: str, company_id: str, expected_version: int) -> Employee:
        """软删员工：状态机 archived→deleted + 写 deleted_at + 清理汇报链闭包。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND company_id = ?",
                (employee_id, company_id),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"员工 {employee_id} 不存在")

            current_status = current["status"]
            allowed = _EMPLOYEE_TRANSITIONS.get(current_status, frozenset())
            if "deleted" not in allowed:
                raise create_error(
                    ORG_STATE_INVALID,
                    f"不允许从 {current_status} 转换到 deleted",
                )

            rc = ReportingClosure()
            # 把该员工的所有直接下属挂到其原上级下，避免悬空
            old_manager_id = current["reports_to_employee_id"]
            cursor = await db.execute(
                "SELECT employee_id, version FROM employees WHERE reports_to_employee_id = ? AND company_id = ? AND deleted_at IS NULL",
                (employee_id, company_id),
            )
            direct_reports = await cursor.fetchall()
            for rep in direct_reports:
                await rc.change_manager(db, company_id, rep["employee_id"], employee_id, old_manager_id)

            # 从汇报链闭包表彻底移除该员工相关记录
            await db.execute(
                "DELETE FROM employee_reporting_closure WHERE company_id = ? AND (ancestor_employee_id = ? OR descendant_employee_id = ?)",
                (company_id, employee_id, employee_id),
            )

            cursor = await db.execute(
                """UPDATE employees
                   SET status = 'deleted', deleted_at = ?, updated_at = ?
                   WHERE employee_id = ? AND company_id = ? AND version = ?""",
                (now, now, employee_id, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: employee {employee_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ?", (employee_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_employee(row)

    async def update(
        self,
        employee_id: str,
        company_id: str,
        expected_version: int,
        updates: dict,
    ) -> Employee:
        """CAS 更新员工。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND company_id = ?",
                (employee_id, company_id),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"员工 {employee_id} 不存在")

            allowed = {"name", "role_name", "reports_to_employee_id", "stability_level",
                        "capability_snapshot", "department_id"}
            set_parts: list[str] = []
            params: list[object] = []
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key == "capability_snapshot":
                    set_parts.append(f"{key} = ?")
                    params.append(json.dumps(value))
                else:
                    set_parts.append(f"{key} = ?")
                    params.append(value)

            if not set_parts:
                raise create_error(ORG_STATE_INVALID, "无可更新字段")

            set_parts.append("version = version + 1")
            set_parts.append("updated_at = ?")
            params.append(now)
            params.extend([employee_id, company_id, expected_version])

            sql = f"""UPDATE employees
                      SET {', '.join(set_parts)}
                      WHERE employee_id = ? AND company_id = ? AND version = ?"""
            cursor = await db.execute(sql, params)
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: employee {employee_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ?", (employee_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_employee(row)

    async def get(self, employee_id: str) -> Optional[Employee]:
        """获取员工。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ?", (employee_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_employee(row)

    async def list_by_company(
        self, company_id: str, status: str | None = None
    ) -> list[Employee]:
        """按公司列出员工。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    """SELECT * FROM employees
                       WHERE company_id = ? AND status = ?
                       ORDER BY created_at""",
                    (company_id, status),
                )
            else:
                cursor = await db.execute(
                    """SELECT * FROM employees
                       WHERE company_id = ?
                       ORDER BY created_at""",
                    (company_id,),
                )
            rows = await cursor.fetchall()
            return [self._row_to_employee(r) for r in rows]

    async def list_by_department(
        self, company_id: str, department_id: str
    ) -> list[Employee]:
        """按部门列出员工。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM employees
                   WHERE company_id = ? AND department_id = ?
                   ORDER BY created_at""",
                (company_id, department_id),
            )
            rows = await cursor.fetchall()
            return [self._row_to_employee(r) for r in rows]

    async def set_manager(
        self,
        employee_id: str,
        company_id: str,
        expected_version: int,
        new_manager_id: str | None,
        operator: str,
    ) -> Employee:
        """设置/变更员工直属上级，同事务维护汇报链闭包表。

        Args:
            employee_id: 目标员工 ID
            company_id: 公司 ID
            expected_version: 乐观锁版本
            new_manager_id: 新上级 ID（None 表示无上级）
            operator: 操作者（LocalOwnerPrincipal.id）

        Returns:
            更新后的 Employee
        """
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. 获取当前员工
            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND company_id = ?",
                (employee_id, company_id),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"员工 {employee_id} 不存在")

            old_manager_id = current["reports_to_employee_id"]
            if old_manager_id == new_manager_id:
                # 无变化
                return self._row_to_employee(current)

            # 2. 校验新上级：同公司、未删除、非自身、非自身下属（防环）
            if new_manager_id is not None:
                cursor = await db.execute(
                    "SELECT employee_id FROM employees WHERE employee_id = ? AND company_id = ? AND deleted_at IS NULL",
                    (new_manager_id, company_id),
                )
                if await cursor.fetchone() is None:
                    raise create_error(ORG_NOT_FOUND, f"新上级 {new_manager_id} 不存在")

                # 防环：新上级不能是当前员工的下属
                rc = ReportingClosure()
                if await rc.check_cycle(db, company_id, employee_id, new_manager_id):
                    raise create_error(
                        ORG_REPORTING_CYCLE,
                        f"设置上级会形成环: {employee_id} -> {new_manager_id}",
                    )

            # 3. 更新员工表 + 维护闭包表（同一事务）
            cursor = await db.execute(
                """UPDATE employees
                   SET reports_to_employee_id = ?, version = version + 1, updated_at = ?
                   WHERE employee_id = ? AND company_id = ? AND version = ?""",
                (new_manager_id, now, employee_id, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: employee {employee_id}",
                )

            # 维护闭包表
            rc = ReportingClosure()
            await rc.change_manager(db, company_id, employee_id, old_manager_id, new_manager_id)

            # 写审计日志
            import uuid
            audit_id = str(uuid.uuid4())
            before = {"reports_to_employee_id": old_manager_id}
            after = {"reports_to_employee_id": new_manager_id}
            await db.execute(
                """INSERT INTO org_change_audit
                   (id, company_id, aggregate_type, aggregate_id, action,
                    before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                   VALUES (?, ?, 'employee', ?, 'manager_changed', ?, ?, ?, '', ?, ?)""",
                (
                    audit_id, company_id, employee_id,
                    json.dumps(before), json.dumps(after),
                    operator, str(uuid.uuid4()), now,
                ),
            )

            await db.commit()

            # 返回更新后的员工
            cursor = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ?", (employee_id,),
            )
            row = await cursor.fetchone()
            return self._row_to_employee(row)
