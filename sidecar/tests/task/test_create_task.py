"""test_create_task：两入口 + 预算/backend 集成（P9-T2）。"""

from __future__ import annotations

import pytest

from acos.task.service import TaskService
from tests.task.conftest import (
    migrated_db, seed_backend, seed_budget_policy, seed_company_employee,
)


@pytest.mark.asyncio
async def test_create_task_company_scope(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    res = await svc.create_task(
        company_id="co1", title="T", manager_employee_id="emp1",
        manager_scope="company", goal="g", acceptance="a",
    )
    assert res["status"] == "created"
    assert res["manager_scope"] == "company"
    assert res["backend_id"] == "be1"
    assert res["budget_currency"] == "CNY"


@pytest.mark.asyncio
async def test_create_task_dept_scope_requires_department_leader(migrated_db):
    db = migrated_db
    await seed_company_employee(db, department_id="depX", leader_employee_id="emp1")
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    # dept scope 无 department_id -> 非法
    with pytest.raises(Exception):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="dept", goal="g", acceptance="a",
        )
    # 带有效 department_id + leader -> 成功
    res = await svc.create_task(
        company_id="co1", title="T", manager_employee_id="emp1",
        manager_scope="dept", goal="g", acceptance="a", department_id="depX",
    )
    assert res["manager_scope"] == "dept"


@pytest.mark.asyncio
async def test_create_task_explicit_budget(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    res = await svc.create_task(
        company_id="co1", title="T", manager_employee_id="emp1",
        manager_scope="company", goal="g", acceptance="a",
        budget={"currency": "USD", "limit_micros": 5_000_000, "token_limit": 1000},
    )
    assert res["budget_currency"] == "USD"
    assert res["budget_limit_micros"] == 5_000_000


@pytest.mark.asyncio
async def test_create_task_no_backend_raises(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_budget_policy(db)
    svc = TaskService(db)
    with pytest.raises(Exception):
        await svc.create_task(
            company_id="co1", title="T", manager_employee_id="emp1",
            manager_scope="company", goal="g", acceptance="a",
        )
