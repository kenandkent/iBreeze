"""汇报链闭包表管理（员工管理层级关系，独立于部门层级）。"""

from __future__ import annotations

import aiosqlite


class ReportingClosure:
    """员工汇报链闭包表管理。

    维护员工之间的管理关系（reports_to_employee_id），与部门闭包表完全独立。
    用于高效查询：某员工的所有下属（含间接）、某员工的所有上级（含间接）。
    """

    async def add_employee(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        employee_id: str,
        reports_to_employee_id: str | None,
    ) -> None:
        """新增员工，维护闭包表。"""
        # 自引用行
        await conn.execute(
            """INSERT INTO employee_reporting_closure
               (company_id, ancestor_employee_id, descendant_employee_id, depth)
               VALUES (?, ?, ?, 0)""",
            (company_id, employee_id, employee_id),
        )

        if reports_to_employee_id is not None:
            # 插入新员工到所有祖先的后代集合
            await conn.execute(
                """INSERT INTO employee_reporting_closure
                   (company_id, ancestor_employee_id, descendant_employee_id, depth)
                   SELECT ?, ancestor_employee_id, ?, depth + 1
                   FROM employee_reporting_closure
                   WHERE company_id = ? AND descendant_employee_id = ?""",
                (company_id, employee_id, company_id, reports_to_employee_id),
            )

    async def change_manager(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        employee_id: str,
        old_manager_id: str | None,
        new_manager_id: str | None,
    ) -> None:
        """变更直属上级，维护闭包表。

        算法与部门闭包相同：
        1. 删除旧连接：旧祖先链(不含自身) × 子树后代(含自身)
        2. 插入新连接：新祖先链(含新上级自身) × 子树后代(含自身)
        """
        # 如果没有变化则返回
        if old_manager_id == new_manager_id:
            return

        # Step 1: 删除旧连接（如果原有上级）
        if old_manager_id is not None:
            await conn.execute(
                """DELETE FROM employee_reporting_closure
                   WHERE company_id = ?
                     AND ancestor_employee_id IN (
                         SELECT ancestor_employee_id FROM employee_reporting_closure
                         WHERE company_id = ? AND descendant_employee_id = ?
                           AND ancestor_employee_id != descendant_employee_id
                     )
                     AND descendant_employee_id IN (
                         SELECT descendant_employee_id FROM employee_reporting_closure
                         WHERE company_id = ? AND ancestor_employee_id = ?
                     )""",
                (company_id, company_id, employee_id, company_id, employee_id),
            )

        # Step 2: 插入新连接（如果有新上级）
        if new_manager_id is not None:
            # 新祖先链：新上级及其所有祖先（含自引用）
            # 子树后代：该员工及其所有后代（含自引用）
            await conn.execute(
                """INSERT INTO employee_reporting_closure
                   (company_id, ancestor_employee_id, descendant_employee_id, depth)
                   SELECT ?, anc.ancestor_employee_id, desc.descendant_employee_id,
                          anc.depth + desc.depth + 1
                   FROM (
                       SELECT ancestor_employee_id, depth FROM employee_reporting_closure
                       WHERE company_id = ? AND descendant_employee_id = ?
                   ) anc
                   CROSS JOIN (
                       SELECT descendant_employee_id, depth FROM employee_reporting_closure
                       WHERE company_id = ? AND ancestor_employee_id = ?
                   ) desc
                   WHERE anc.ancestor_employee_id != desc.descendant_employee_id""",
                (
                    company_id,
                    company_id, new_manager_id,
                    company_id, employee_id,
                ),
            )

    async def get_subordinates(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        employee_id: str,
    ) -> list[str]:
        """获取所有下属（含间接，不含自身）。"""
        cursor = await conn.execute(
            """SELECT descendant_employee_id FROM employee_reporting_closure
               WHERE company_id = ? AND ancestor_employee_id = ? AND depth > 0
               ORDER BY depth""",
            (company_id, employee_id),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_superiors(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        employee_id: str,
    ) -> list[str]:
        """获取所有上级（含间接，不含自身）。"""
        cursor = await conn.execute(
            """SELECT ancestor_employee_id FROM employee_reporting_closure
               WHERE company_id = ? AND descendant_employee_id = ? AND depth > 0
               ORDER BY depth""",
            (company_id, employee_id),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def check_cycle(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        employee_id: str,
        target_manager_id: str,
    ) -> bool:
        """检查是否会形成环。如果 target_manager_id 是 employee_id 的下属，返回 True。"""
        if employee_id == target_manager_id:
            return True
        cursor = await conn.execute(
            """SELECT 1 FROM employee_reporting_closure
               WHERE company_id = ?
                 AND ancestor_employee_id = ?
                 AND descendant_employee_id = ?
                 AND depth > 0
               LIMIT 1""",
            (company_id, employee_id, target_manager_id),
        )
        row = await cursor.fetchone()
        return row is not None

    async def rebuild_for_company(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
    ) -> None:
        """为公司重建整个闭包表（用于数据修复或迁移）。"""
        # 清空该公司数据
        await conn.execute(
            "DELETE FROM employee_reporting_closure WHERE company_id = ?",
            (company_id,),
        )

        # 获取该公司所有员工
        cursor = await conn.execute(
            "SELECT employee_id, reports_to_employee_id FROM employees WHERE company_id = ? AND deleted_at IS NULL",
            (company_id,),
        )
        employees = await cursor.fetchall()

        # 按层级构建：先插入根节点，再逐层插入
        # 简化：先插入自引用，再按 reports_to 关系插入
        for employee_id, reports_to in employees:
            await self.add_employee(conn, company_id, employee_id, reports_to)