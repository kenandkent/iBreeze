"""Department and employee aggregate tests."""

from __future__ import annotations

import aiosqlite
import pytest

from ibreeze.company import create_company
from ibreeze.employee import (
    create_department,
    create_employee,
    get_department,
    get_employee,
    list_departments,
    list_employees,
    set_department_leader,
    update_department,
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


async def _company(db: aiosqlite.Connection, profile_id: str):
    return await create_company(
        db,
        CompanyCreate(
            name="交付公司",
            introduction="架构、开发、测试依次流转",
            general_manager_name="总经理",
            base_profile_version_id=profile_id,
        ),
    )


@pytest.mark.asyncio
async def test_department_employee_lifecycle(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile)
    department = await create_department(
        db,
        company.id,
        DepartmentCreate(
            name="开发部",
            function_description="实现代码并完成单元测试",
            leader_name="开发负责人",
            base_profile_version_id=published_profile,
        ),
    )
    assert department.department_type == "standard"
    assert (await get_department(db, company.id, department.id)).id == department.id
    assert len(await list_departments(db, company.id)) == 2

    member = await create_employee(
        db,
        company.id,
        department.id,
        EmployeeCreate(
            display_name="工程师",
            base_profile_version_id=published_profile,
            workflow_role=WorkflowRole.MEMBER,
        ),
    )
    assert (await get_employee(db, company.id, member.id)).department_id == department.id
    assert len(
        await list_employees(
            db,
            company.id,
            department_id=department.id,
        )
    ) == 2

    renamed = await update_employee_display_name(
        db,
        company.id,
        member.id,
        EmployeeUpdateDisplay(display_name="高级工程师", expected_version=1),
    )
    assert renamed.display_name == "高级工程师"
    assert renamed.version == 2

    new_leader = await set_department_leader(
        db,
        company.id,
        department.id,
        member.id,
        expected_version=1,
    )
    assert new_leader.leader_employee_id == member.id
    assert (await get_employee(db, company.id, member.id)).workflow_role == "department_leader"

    inactive = await update_employee_status(
        db,
        company.id,
        department.leader_employee_id,
        EmployeeStatus.INACTIVE,
        expected_version=2,
    )
    assert inactive.status == "inactive"


@pytest.mark.asyncio
async def test_department_update_is_revisioned_and_scoped(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile)
    department = await create_department(
        db,
        company.id,
        DepartmentCreate(
            name="测试部",
            function_description="编写并执行验收测试",
            leader_name="测试负责人",
            base_profile_version_id=published_profile,
        ),
    )
    updated = await update_department(
        db,
        company.id,
        department.id,
        DepartmentUpdate(
            function_description="编写测试、执行首测和终测",
            expected_version=1,
        ),
    )
    assert updated.version == 2
    revision = await (
        await db.execute(
            "SELECT function_description FROM department_revisions WHERE id=?",
            (updated.current_revision_id,),
        )
    ).fetchone()
    assert revision[0] == "编写测试、执行首测和终测"
    with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
        await get_department(db, "00000000-0000-4000-8000-000000000000", department.id)


@pytest.mark.asyncio
async def test_employee_rejects_invalid_role_and_stale_write(
    db: aiosqlite.Connection,
    published_profile: str,
) -> None:
    company = await _company(db, published_profile)
    department = await create_department(
        db,
        company.id,
        DepartmentCreate(
            name="架构部",
            function_description="编写需求、设计和实施计划",
            leader_name="架构负责人",
            base_profile_version_id=published_profile,
        ),
    )
    with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
        await create_employee(
            db,
            company.id,
            department.id,
            EmployeeCreate(
                display_name="伪负责人",
                base_profile_version_id=published_profile,
                workflow_role=WorkflowRole.DEPARTMENT_LEADER,
            ),
        )
    leader = await get_employee(db, company.id, department.leader_employee_id)
    with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
        await update_employee_display_name(
            db,
            company.id,
            leader.id,
            EmployeeUpdateDisplay(display_name="过期修改", expected_version=99),
        )
