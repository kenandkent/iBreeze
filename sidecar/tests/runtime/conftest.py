"""Phase 7 runtime 测试公共 fixture。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.runtime.session_thread_store import SessionThreadStore
from acos.store.migrator import Migrator

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture
async def migrated_db(tmp_path: Path) -> tuple[str, str]:
    """返回 (db_path, company_root)，已应用全部迁移。"""
    db_path = str(tmp_path / "test.db")
    company_root = str(tmp_path / "sessions_root")
    Path(company_root).mkdir(parents=True, exist_ok=True)
    migrator = Migrator(db_path)
    await migrator.run_pending_migrations(MIGRATIONS_DIR)
    return db_path, company_root


@pytest.fixture
async def store(migrated_db) -> SessionThreadStore:
    db_path, company_root = migrated_db
    return SessionThreadStore(db_path, company_root)


async def seed_company_employee(
    db_path: str, *, company_id: str = "co1", department_id: str = "dep1",
    employee_id: str = "emp1", capability_snapshot: str = "{}",
    status: str = "active",
) -> dict[str, str]:
    """直接落库一个公司+部门+职员，供 Phase 7 测试使用。"""
    import aiosqlite
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO companies (company_id, name, status, default_provider_policy,
               root_department_id, version, created_at, updated_at)
               VALUES (?, '公司', 'active', '{}', ?, 1, ?, ?)""",
            (company_id, department_id, now, now),
        )
        await db.execute(
            """INSERT OR IGNORE INTO departments (department_id, company_id, name, status,
               version, created_at, updated_at)
               VALUES (?, ?, '部门', 'active', 1, ?, ?)""",
            (department_id, company_id, now, now),
        )
        await db.execute(
            """INSERT INTO employees (employee_id, company_id, department_id, template_id,
               capability_snapshot, name, role_name, employee_type, stability_level,
               status, session_transfer_state, version, created_at, updated_at)
               VALUES (?, ?, ?, 'tpl', ?, '员工', '', 'employee', 5, ?, 'none', 1, ?, ?)""",
            (employee_id, company_id, department_id, capability_snapshot, status, now, now),
        )
        await db.commit()
    return {"company_id": company_id, "department_id": department_id, "employee_id": employee_id}

