"""员工排空服务 - 处理员工转移、挂起、归档等排空操作。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.organization.models import EmployeeDrain
from acos.rpc.errors import (
    ORG_NOT_FOUND,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)


class EmployeeDrainService:
    """员工排空服务。"""

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
    def _row_to_drain(row: aiosqlite.Row) -> EmployeeDrain:
        return EmployeeDrain(
            drain_id=row["drain_id"],
            company_id=row["company_id"],
            employee_id=row["employee_id"],
            operation=row["operation"],
            target_department_id=row["target_department_id"],
            status=row["status"],
            intervention_id=row["intervention_id"],
            timeout_seconds=row["timeout_seconds"],
        )

    async def start_drain(
        self,
        company_id: str,
        employee_id: str,
        operation: str,
        target_department_id: str | None = None,
        timeout_seconds: int = 600,
    ) -> EmployeeDrain:
        """启动排空操作。"""
        now = self._now()
        drain = EmployeeDrain(
            company_id=company_id,
            employee_id=employee_id,
            operation=operation,
            target_department_id=target_department_id,
            status="active",
            timeout_seconds=timeout_seconds,
        )

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO employee_drains
                   (drain_id, company_id, employee_id, operation,
                    target_department_id, status, intervention_id,
                    timeout_seconds, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', NULL, ?, ?, ?)""",
                (
                    drain.drain_id, drain.company_id, drain.employee_id,
                    drain.operation, drain.target_department_id,
                    drain.timeout_seconds, now, now,
                ),
            )
            await db.commit()
        return drain

    async def resolve_drain(
        self,
        drain_id: str,
        company_id: str,
        expected_status: str,
        result_status: str,
    ) -> EmployeeDrain:
        """解决排空操作（CAS 状态更新）。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """UPDATE employee_drains
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE drain_id = ? AND company_id = ? AND status = ?""",
                (result_status, now, drain_id, company_id, expected_status),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突或状态无效: drain {drain_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM employee_drains WHERE drain_id = ?", (drain_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_drain(row)

    async def abort_drains_by_dissolution(self, company_id: str) -> int:
        """公司解散时中止所有活跃排空。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """UPDATE employee_drains
                   SET status = 'aborted_by_dissolution', updated_at = ?
                   WHERE company_id = ? AND status = 'active'""",
                (now, company_id),
            )
            await db.commit()
            return cursor.rowcount

    async def get(self, drain_id: str) -> Optional[EmployeeDrain]:
        """获取排空记录。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM employee_drains WHERE drain_id = ?", (drain_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_drain(row)

    async def list_by_employee(
        self, company_id: str, employee_id: str, status: str | None = None
    ) -> list[EmployeeDrain]:
        """按员工列出排空记录。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    """SELECT * FROM employee_drains
                       WHERE company_id = ? AND employee_id = ? AND status = ?
                       ORDER BY created_at""",
                    (company_id, employee_id, status),
                )
            else:
                cursor = await db.execute(
                    """SELECT * FROM employee_drains
                       WHERE company_id = ? AND employee_id = ?
                       ORDER BY created_at""",
                    (company_id, employee_id),
                )
            rows = await cursor.fetchall()
            return [self._row_to_drain(r) for r in rows]
