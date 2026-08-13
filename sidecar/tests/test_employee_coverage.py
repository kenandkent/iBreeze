"""Coverage-focused tests for department/employee aggregate error and pagination branches."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.employee import (
    create_department,
    create_employee,
    get_employee,
    list_departments,
    list_employees,
    set_department_leader,
    transfer_employee,
    update_department,
    update_employee_base_profile,
    update_employee_display_name,
    update_employee_status,
)
from ibreeze.schemas import (
    CompanyCreate,
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeStatus,
    EmployeeUpdateDisplay,
    WorkflowRole,
)


async def _company(db: aiosqlite.Connection, profile_id: str, name: str):
    return await create_company(
        db,
        CompanyCreate(
            name=name,
            introduction="覆盖部门与员工分支",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


async def _department(db: aiosqlite.Connection, company_id: str, profile_id: str, name: str):
    return await create_department(
        db,
        company_id,
        DepartmentCreate(
            name=name,
            function_description="覆盖部门逻辑",
            leader_name=f"{name}负责人",
            base_profile_version_id=profile_id,
        ),
    )


async def _member(db: aiosqlite.Connection, company_id: str, department_id: str, profile_id: str, name: str):
    return await create_employee(
        db,
        company_id,
        department_id,
        EmployeeCreate(
            display_name=name,
            base_profile_version_id=profile_id,
            workflow_role=WorkflowRole.MEMBER,
        ),
    )


async def _insert_active_assignment(db: aiosqlite.Connection, company_id: str, employee_id: str) -> None:
    """Insert a running employee_tasks row (FKs disabled for a standalone fixture)."""
    await db.execute("PRAGMA foreign_keys = OFF")
    now = "2026-01-01T00:00:00.000000Z"
    await db.execute(
        """INSERT INTO employee_tasks
           (id, company_id, department_task_id, employee_id, task_kind, objective,
            acceptance_criteria_json, status, resume_state, created_at, updated_at, version)
           VALUES (?, ?, ?, ?, 'standard', '覆盖目标', '[]', 'running', NULL, ?, ?, 1)""",
        (str(uuid.uuid4()), company_id, str(uuid.uuid4()), employee_id, now, now),
    )


# ── create_department ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_department_rejects_unpublished_profile(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "无效档案公司")
    with pytest.raises(ValueError, match="PROFILE_VERSION_INVALID"):
        await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="开发部",
                function_description="描述",
                leader_name="负责人",
                base_profile_version_id=str(uuid.uuid4()),
            ),
        )


@pytest.mark.asyncio
async def test_create_department_rejects_missing_company(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await create_department(
            db,
            str(uuid.uuid4()),
            DepartmentCreate(
                name="开发部",
                function_description="描述",
                leader_name="负责人",
                base_profile_version_id=published_profile,
            ),
        )


@pytest.mark.asyncio
async def test_create_department_rejects_archived_company(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "归档部门公司")
    await db.execute("UPDATE companies SET status='archived' WHERE id=?", (company.id,))
    await db.commit()
    with pytest.raises(ValueError, match="COMPANY_ARCHIVED"):
        await create_department(
            db,
            company.id,
            DepartmentCreate(
                name="开发部",
                function_description="描述",
                leader_name="负责人",
                base_profile_version_id=published_profile,
            ),
        )


@pytest.mark.asyncio
async def test_create_department_requires_write_queue(
    local_db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company_id = (
        await (await local_db.execute("SELECT id FROM companies LIMIT 1")).fetchone()
    )["id"]
    with pytest.raises(RuntimeError, match="WRITE_QUEUE_REQUIRED"):
        await create_department(
            local_db,
            company_id,
            DepartmentCreate(
                name="开发部",
                function_description="描述",
                leader_name="负责人",
                base_profile_version_id=published_profile,
            ),
        )


@pytest.mark.asyncio
async def test_create_department_rejects_duplicate_name(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "重名部门公司")
    await _department(db, company.id, published_profile, "开发部")
    with pytest.raises(ValueError, match="NAME_EXISTS"):
        await _department(db, company.id, published_profile, "开发部")


@pytest.mark.asyncio
async def test_list_departments_pagination_after(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "部门分页公司")
    await _department(db, company.id, published_profile, "一部")
    await _department(db, company.id, published_profile, "二部")
    all_departments = await list_departments(db, company.id)
    anchor = all_departments[-1]
    row = await (
        await db.execute("SELECT created_at FROM departments WHERE id=?", (anchor.id,))
    ).fetchone()
    after = await list_departments(db, company.id, after=(row[0], anchor.id))
    assert anchor.id not in [d.id for d in after]


# ── update_department ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_department_optimistic_lock_conflict(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "更新冲突公司")
    department = await _department(db, company.id, published_profile, "冲突部")
    with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
        await update_department(
            db,
            company.id,
            department.id,
            DepartmentUpdate(name="新名", expected_version=99),
        )


@pytest.mark.asyncio
async def test_update_department_rejects_non_active(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "停用更新公司")
    department = await _department(db, company.id, published_profile, "停用部")
    await db.execute("UPDATE departments SET status='archived' WHERE id=?", (department.id,))
    await db.commit()
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await update_department(
            db,
            company.id,
            department.id,
            DepartmentUpdate(function_description="新描述", expected_version=1),
        )


@pytest.mark.asyncio
async def test_update_department_rejects_duplicate_name(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "改名冲突公司")
    first = await _department(db, company.id, published_profile, "甲部")
    await _department(db, company.id, published_profile, "乙部")
    with pytest.raises(ValueError, match="NAME_EXISTS"):
        await update_department(
            db,
            company.id,
            first.id,
            DepartmentUpdate(name="乙部", expected_version=1),
        )


# ── create_employee ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_employee_requires_write_queue(
    local_db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company_id = (
        await (await local_db.execute("SELECT id FROM companies LIMIT 1")).fetchone()
    )["id"]
    department_id = (
        await (await local_db.execute("SELECT id FROM departments LIMIT 1")).fetchone()
    )["id"]
    with pytest.raises(RuntimeError, match="WRITE_QUEUE_REQUIRED"):
        await create_employee(
            local_db,
            company_id,
            department_id,
            EmployeeCreate(
                display_name="工程师",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )


@pytest.mark.asyncio
async def test_create_employee_rejects_missing_department(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "缺部门公司")
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await create_employee(
            db,
            company.id,
            str(uuid.uuid4()),
            EmployeeCreate(
                display_name="工程师",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.MEMBER,
            ),
        )


@pytest.mark.asyncio
async def test_create_employee_rejects_duplicate_name(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "员工重名公司")
    department = await _department(db, company.id, published_profile, "重名部")
    await _member(db, company.id, department.id, published_profile, "工程师")
    with pytest.raises(ValueError, match="NAME_EXISTS"):
        await _member(db, company.id, department.id, published_profile, "工程师")


@pytest.mark.asyncio
async def test_get_employee_not_found(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "查无员工公司")
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await get_employee(db, company.id, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_list_employees_pagination_after_company_wide(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "员工分页公司")
    department = await _department(db, company.id, published_profile, "分页部")
    await _member(db, company.id, department.id, published_profile, "工程师甲")
    await _member(db, company.id, department.id, published_profile, "工程师乙")
    all_employees = await list_employees(db, company.id)
    anchor = all_employees[-1]
    row = await (
        await db.execute("SELECT created_at FROM employees WHERE id=?", (anchor.id,))
    ).fetchone()
    after = await list_employees(db, company.id, after=(row[0], anchor.id))
    assert anchor.id not in [e.id for e in after]


@pytest.mark.asyncio
async def test_list_employees_pagination_department_after(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "部门员工分页公司")
    department = await _department(db, company.id, published_profile, "分页二部")
    await _member(db, company.id, department.id, published_profile, "工程师丙")
    await _member(db, company.id, department.id, published_profile, "工程师丁")
    all_employees = await list_employees(db, company.id, department_id=department.id)
    anchor = all_employees[-1]
    row = await (
        await db.execute("SELECT created_at FROM employees WHERE id=?", (anchor.id,))
    ).fetchone()
    after = await list_employees(
        db,
        company.id,
        department_id=department.id,
        after=(row[0], anchor.id),
    )
    assert anchor.id not in [e.id for e in after]


# ── update_employee_display_name ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_display_name_rejects_duplicate(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "改名冲突公司")
    department = await _department(db, company.id, published_profile, "改名部")
    first = await _member(db, company.id, department.id, published_profile, "甲")
    await _member(db, company.id, department.id, published_profile, "乙")
    with pytest.raises(ValueError, match="NAME_EXISTS"):
        await update_employee_display_name(
            db,
            company.id,
            first.id,
            EmployeeUpdateDisplay(display_name="乙", expected_version=1),
        )


# ── update_employee_base_profile ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_employee_base_profile(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "档案更新公司")
    department = await _department(db, company.id, published_profile, "档案部")
    member = await _member(db, company.id, department.id, published_profile, "档案员工")
    updated = await update_employee_base_profile(
        db,
        company.id,
        member.id,
        published_profile,
        expected_version=1,
    )
    assert updated.version == 2
    assert updated.base_profile_version_id == published_profile
    with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
        await update_employee_base_profile(
            db,
            company.id,
            member.id,
            published_profile,
            expected_version=99,
        )


# ── update_employee_status ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_status_rejects_general_manager(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "总经理公司")
    gm = await get_employee(db, company.id, company.general_manager_employee_id)
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await update_employee_status(
            db,
            company.id,
            gm.id,
            EmployeeStatus.INACTIVE,
            expected_version=gm.version,
        )


@pytest.mark.asyncio
async def test_update_status_rejects_active_assignment(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "有任务公司")
    department = await _department(db, company.id, published_profile, "任务部")
    member = await _member(db, company.id, department.id, published_profile, "任务员工")
    await _insert_active_assignment(db, company.id, member.id)
    with pytest.raises(ValueError, match="EMPLOYEE_HAS_ACTIVE_ASSIGNMENT"):
        await update_employee_status(
            db,
            company.id,
            member.id,
            EmployeeStatus.UNAVAILABLE,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_update_status_optimistic_lock_conflict(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "状态冲突公司")
    department = await _department(db, company.id, published_profile, "状态部")
    member = await _member(db, company.id, department.id, published_profile, "状态员工")
    with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
        await update_employee_status(
            db,
            company.id,
            member.id,
            EmployeeStatus.INACTIVE,
            expected_version=99,
        )


# ── transfer_employee ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transfer_employee_happy_path(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "调岗公司")
    source = await _department(db, company.id, published_profile, "原部门")
    target = await _department(db, company.id, published_profile, "新部门")
    member = await _member(db, company.id, source.id, published_profile, "调岗员工")
    transferred = await transfer_employee(
        db,
        company.id,
        member.id,
        target.id,
        expected_version=1,
    )
    assert transferred.department_id == target.id
    assert transferred.version == 2


@pytest.mark.asyncio
async def test_transfer_rejects_general_manager(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "调岗总经理公司")
    target = await _department(db, company.id, published_profile, "目标部")
    gm = await get_employee(db, company.id, company.general_manager_employee_id)
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await transfer_employee(
            db,
            company.id,
            gm.id,
            target.id,
            expected_version=gm.version,
        )


@pytest.mark.asyncio
async def test_transfer_rejects_active_assignment(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "调岗有任务公司")
    source = await _department(db, company.id, published_profile, "任务源部")
    target = await _department(db, company.id, published_profile, "任务标部")
    member = await _member(db, company.id, source.id, published_profile, "任务调岗员工")
    await _insert_active_assignment(db, company.id, member.id)
    with pytest.raises(ValueError, match="EMPLOYEE_HAS_ACTIVE_ASSIGNMENT"):
        await transfer_employee(
            db,
            company.id,
            member.id,
            target.id,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_transfer_rejects_missing_target_department(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "调岗缺部门公司")
    source = await _department(db, company.id, published_profile, "调岗源部")
    member = await _member(db, company.id, source.id, published_profile, "缺目标员工")
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await transfer_employee(
            db,
            company.id,
            member.id,
            str(uuid.uuid4()),
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_transfer_optimistic_lock_conflict(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "调岗冲突公司")
    source = await _department(db, company.id, published_profile, "冲突源部")
    target = await _department(db, company.id, published_profile, "冲突标部")
    member = await _member(db, company.id, source.id, published_profile, "冲突员工")
    with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
        await transfer_employee(
            db,
            company.id,
            member.id,
            target.id,
            expected_version=99,
        )


# ── set_department_leader ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_leader_rejects_gm_office(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "总经理办公室公司")
    gm = await get_employee(db, company.id, company.general_manager_employee_id)
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await set_department_leader(
            db,
            company.id,
            company.general_manager_office_id,
            gm.id,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_set_leader_noop_when_already_leader(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "已是负责人公司")
    department = await _department(db, company.id, published_profile, "负责人部")
    result = await set_department_leader(
        db,
        company.id,
        department.id,
        department.leader_employee_id,
        expected_version=department.version,
    )
    assert result.leader_employee_id == department.leader_employee_id


@pytest.mark.asyncio
async def test_set_leader_optimistic_lock_conflict(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile, "负责人冲突公司")
    department = await _department(db, company.id, published_profile, "负责人冲突部")
    member = await _member(db, company.id, department.id, published_profile, "新负责人")
    with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
        await set_department_leader(
            db,
            company.id,
            department.id,
            member.id,
            expected_version=99,
        )
