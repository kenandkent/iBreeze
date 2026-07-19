"""部门闭包表管理。"""

from __future__ import annotations

import aiosqlite


class DepartmentClosure:
    """部门闭包表管理。"""

    async def add_department(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        department_id: str,
        parent_id: str | None,
    ) -> None:
        """新增部门，维护闭包表。"""
        if parent_id is None:
            await conn.execute(
                """INSERT INTO department_closure
                   (company_id, ancestor_department_id, descendant_department_id, depth)
                   VALUES (?, ?, ?, 0)""",
                (company_id, department_id, department_id),
            )
            return

        await conn.execute(
            """INSERT INTO department_closure
               (company_id, ancestor_department_id, descendant_department_id, depth)
               VALUES (?, ?, ?, 0)""",
            (company_id, department_id, department_id),
        )

        await conn.execute(
            """INSERT INTO department_closure
               (company_id, ancestor_department_id, descendant_department_id, depth)
               SELECT ?, ancestor_department_id, ?, depth + 1
               FROM department_closure
               WHERE company_id = ? AND descendant_department_id = ?""",
            (company_id, department_id, company_id, parent_id),
        )

    async def move_subtree(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        department_id: str,
        new_parent_id: str,
    ) -> None:
        """移动子树到新父节点。

        算法：
        1. 删除所有"旧祖先链→子树后代"的外部连接（保留子树内部关系和自引用）
        2. 插入"新祖先链→子树后代"的新连接
        """
        # Step 1: 删除旧连接
        # 删除 ancestor ∈ 旧祖先链(不含自身) 且 descendant ∈ 子树(含自身) 的条目
        await conn.execute(
            """DELETE FROM department_closure
               WHERE company_id = ?
                 AND ancestor_department_id IN (
                     SELECT ancestor_department_id FROM department_closure
                     WHERE company_id = ? AND descendant_department_id = ?
                       AND ancestor_department_id != descendant_department_id
                 )
                 AND descendant_department_id IN (
                     SELECT descendant_department_id FROM department_closure
                     WHERE company_id = ? AND ancestor_department_id = ?
                 )""",
            (company_id, company_id, department_id, company_id, department_id),
        )

        # Step 2: 插入新连接
        # 新祖先链(new_parent 的祖先含自身) × 子树后代(含自身)
        await conn.execute(
            """INSERT INTO department_closure
               (company_id, ancestor_department_id, descendant_department_id, depth)
               SELECT ?, anc.ancestor_department_id, desc.descendant_department_id,
                      anc.depth + desc.depth + 1
               FROM (
                   SELECT ancestor_department_id, depth FROM department_closure
                   WHERE company_id = ? AND descendant_department_id = ?
               ) anc
               CROSS JOIN (
                   SELECT descendant_department_id, depth FROM department_closure
                   WHERE company_id = ? AND ancestor_department_id = ?
               ) desc
               WHERE anc.ancestor_department_id != desc.descendant_department_id""",
            (
                company_id,
                company_id, new_parent_id,
                company_id, department_id,
            ),
        )

    async def get_descendants(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        department_id: str,
    ) -> list[str]:
        """获取所有后代。"""
        cursor = await conn.execute(
            """SELECT descendant_department_id FROM department_closure
               WHERE company_id = ? AND ancestor_department_id = ? AND depth > 0
               ORDER BY depth""",
            (company_id, department_id),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_ancestors(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        department_id: str,
    ) -> list[str]:
        """获取所有祖先。"""
        cursor = await conn.execute(
            """SELECT ancestor_department_id FROM department_closure
               WHERE company_id = ? AND descendant_department_id = ? AND depth > 0
               ORDER BY depth""",
            (company_id, department_id),
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def check_cycle(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        department_id: str,
        target_parent_id: str,
    ) -> bool:
        """检查是否会形成环。如果 target_parent_id 是 department_id 的后代，返回 True。"""
        if department_id == target_parent_id:
            return True
        cursor = await conn.execute(
            """SELECT 1 FROM department_closure
               WHERE company_id = ?
                 AND ancestor_department_id = ?
                 AND descendant_department_id = ?
                 AND depth > 0
               LIMIT 1""",
            (company_id, department_id, target_parent_id),
        )
        row = await cursor.fetchone()
        return row is not None
