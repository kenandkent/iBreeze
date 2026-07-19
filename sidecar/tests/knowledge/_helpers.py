"""知识库测试共享 helper：初始化完整 DB 与组织数据。"""

from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

from acos.store.migrator import Migrator

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def setup_db(tmp_path) -> str:
    db_path = str(tmp_path / "kg_test.db")
    migrator = Migrator(db_path)
    await migrator.run_pending_migrations(MIGRATIONS_DIR)
    return db_path


async def seed_company(db_path: str, company_id: str = "comp_a") -> None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO companies (company_id, name, status, version, created_at, updated_at)
               VALUES (?, 'C', 'active', 1, ?, ?)""",
            (company_id, _now(), _now()),
        )
        await db.commit()


async def insert_department(db_path, company_id, department_id, parent_id, leader=None):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO departments
                  (department_id, company_id, parent_department_id, name, status, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', 1, ?, ?)""",
            (department_id, company_id, parent_id, department_id, _now(), _now()),
        )
        await db.execute(
            "INSERT INTO department_closure (company_id, ancestor_department_id, descendant_department_id, depth) VALUES (?, ?, ?, 0)",
            (company_id, department_id, department_id),
        )
        if parent_id:
            cur = await db.execute(
                "SELECT ancestor_department_id, depth FROM department_closure WHERE company_id = ? AND descendant_department_id = ?",
                (company_id, parent_id),
            )
            for r in await cur.fetchall():
                await db.execute(
                    "INSERT INTO department_closure (company_id, ancestor_department_id, descendant_department_id, depth) VALUES (?, ?, ?, ?)",
                    (company_id, r["ancestor_department_id"], department_id, r["depth"] + 1),
                )
        if leader is not None:
            await db.execute(
                "UPDATE departments SET leader_employee_id = ? WHERE department_id = ?",
                (leader, department_id),
            )
        await db.commit()


async def make_employee(db_path, company_id, department_id, employee_id, employee_type="employee", template_id="tpl-default"):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO employees
                  (employee_id, company_id, department_id, template_id, name, employee_type, status, version, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)""",
            (employee_id, company_id, department_id, template_id, employee_id, employee_type, _now(), _now()),
        )
        await db.commit()


async def insert_knowledge_source(db_path, company_id, source_type, source_id, source_record_id):
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO knowledge_sources
                  (source_record_id, company_id, source_type, source_id, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?)""",
            (source_record_id, company_id, source_type, source_id, _now(), _now()),
        )
        await db.commit()
