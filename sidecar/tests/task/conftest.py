"""Phase 9 任务工作流测试公共 fixture。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite
import pytest

from acos.store.migrator import Migrator

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture
async def migrated_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    migrator = Migrator(db_path)
    await migrator.run_pending_migrations(MIGRATIONS_DIR)
    return db_path


async def seed_company_employee(
    db_path: str, *,
    company_id: str = "co1",
    department_id: Optional[str] = "dep1",
    employee_id: str = "emp1",
    capability_snapshot: str = "{}",
    status: str = "active",
    employee_type: str = "employee",
    leader_employee_id: Optional[str] = None,
    dept_status: str = "active",
) -> dict[str, str]:
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT OR IGNORE INTO companies
               (company_id, name, status, default_provider_policy, root_department_id,
                version, created_at, updated_at)
               VALUES (?, '公司', 'active', '{}', ?, 1, ?, ?)""",
            (company_id, department_id, now, now),
        )
        if department_id:
            await db.execute(
                """INSERT OR IGNORE INTO departments
                   (department_id, company_id, name, status, leader_employee_id,
                    version, created_at, updated_at)
                   VALUES (?, ?, '部门', ?, ?, 1, ?, ?)""",
                (department_id, company_id, dept_status, leader_employee_id, now, now),
            )
        await db.execute(
            """INSERT OR IGNORE INTO employees
               (employee_id, company_id, department_id, template_id, capability_snapshot,
                name, role_name, employee_type, stability_level, status,
                session_transfer_state, version, created_at, updated_at)
               VALUES (?, ?, ?, 'tpl', ?, '员工', '', ?, 5, ?, 'none', 1, ?, ?)""",
            (employee_id, company_id, department_id, capability_snapshot, employee_type,
             status, now, now),
        )
        await db.commit()
    return {
        "company_id": company_id,
        "department_id": department_id or "",
        "employee_id": employee_id,
    }


async def seed_backend(
    db_path: str, *, company_id: str = "co1", backend_id: str = "be1",
    health: str = "healthy", status: str = "enabled", concurrency: int = 4,
) -> str:
    import json
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO backends
               (backend_id, company_id, name, backend_type, status, health_status,
                capabilities, workspace_types, workspace_root, concurrency_limit,
                version, created_at, updated_at)
               VALUES (?, ?, 'bk', 'local', ?, ?, '[]', '[]', '/tmp', ?, 1, ?, ?)""",
            (backend_id, company_id, status, health, concurrency, now, now),
        )
        await db.commit()
    return backend_id


async def seed_budget_policy(
    db_path: str, *, company_id: str = "co1", currency: str = "CNY",
    monthly: int = 1_000_000_000, per_task: int = 100_000_000,
    on_exceeded: str = "abort",
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO budget_policies
               (policy_id, company_id, name, monthly_limit, per_task_limit, currency,
                on_budget_exceeded, version, status, created_at)
               VALUES (?, ?, '默认', ?, ?, ?, ?, 1, 'active', ?)""",
            (f"bp-{company_id}", company_id, monthly, per_task, currency,
             on_exceeded, now),
        )
        await db.commit()
