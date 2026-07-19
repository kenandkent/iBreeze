"""员工测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.models import EmployeeTemplate, Employee
from acos.organization.service import OrganizationService
from acos.organization.template_service import TemplateService
from acos.organization.employee_service import EmployeeService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def setup(tmp_path: Path) -> tuple[EmployeeService, str, str]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)
    template_svc = TemplateService(str(db_path))
    template = await template_svc.create(
        company_id=company.company_id,
        capability_id="cap-001",
        capability_version=1,
        default_role="开发者",
    )
    await template_svc.activate(template.template_id, company.company_id, expected_version=1)
    return EmployeeService(str(db_path)), company.company_id, template.template_id


async def test_create_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id,
        department_id="dept-1",
        template_id=template_id,
        name="张三",
    )
    assert emp.employee_id
    assert emp.name == "张三"
    assert emp.status == "created"
    assert emp.version == 1
    assert emp.company_id == company_id


async def test_get_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="李四",
    )
    fetched = await svc.get(emp.employee_id)
    assert fetched is not None
    assert fetched.name == "李四"


async def test_get_nonexistent_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, _, _ = setup
    result = await svc.get("nonexistent")
    assert result is None


async def test_activate_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="王五",
    )
    activated = await svc.activate(emp.employee_id, company_id, expected_version=1)
    assert activated.status == "active"
    assert activated.version == 2


async def test_suspend_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="赵六",
    )
    await svc.activate(emp.employee_id, company_id, expected_version=1)
    suspended = await svc.suspend(emp.employee_id, company_id, expected_version=2)
    assert suspended.status == "suspended"


async def test_resume_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="孙七",
    )
    await svc.activate(emp.employee_id, company_id, expected_version=1)
    await svc.suspend(emp.employee_id, company_id, expected_version=2)
    resumed = await svc.resume(emp.employee_id, company_id, expected_version=3)
    assert resumed.status == "active"


async def test_archive_employee(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="周八",
    )
    await svc.activate(emp.employee_id, company_id, expected_version=1)
    archived = await svc.archive(emp.employee_id, company_id, expected_version=2)
    assert archived.status == "archived"


async def test_invalid_transition(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="测试",
    )
    with pytest.raises(AcosError) as exc_info:
        await svc.archive(emp.employee_id, company_id, expected_version=1)
    assert exc_info.value.code == "ORG-STATE-INVALID"


async def test_update_employee_cas(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="原名",
    )
    updated = await svc.update(
        emp.employee_id, company_id, expected_version=1,
        updates={"name": "新名", "role_name": "高级开发者"},
    )
    assert updated.name == "新名"
    assert updated.role_name == "高级开发者"
    assert updated.version == 2


async def test_update_cas_conflict(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="dept-1",
        template_id=template_id, name="原名",
    )
    await svc.update(emp.employee_id, company_id, expected_version=1, updates={"name": "A"})
    with pytest.raises(AcosError) as exc_info:
        await svc.update(emp.employee_id, company_id, expected_version=1, updates={"name": "B"})
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_list_by_company(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    await svc.create(company_id=company_id, department_id="d1", template_id=template_id, name="A")
    await svc.create(company_id=company_id, department_id="d2", template_id=template_id, name="B")
    emps = await svc.list_by_company(company_id)
    assert len(emps) == 2


async def test_list_by_department(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    await svc.create(company_id=company_id, department_id="d1", template_id=template_id, name="A")
    await svc.create(company_id=company_id, department_id="d1", template_id=template_id, name="B")
    await svc.create(company_id=company_id, department_id="d2", template_id=template_id, name="C")
    emps = await svc.list_by_department(company_id, "d1")
    assert len(emps) == 2


async def test_suspend_from_created_fails(setup: tuple[EmployeeService, str, str]) -> None:
    svc, company_id, template_id = setup
    emp = await svc.create(
        company_id=company_id, department_id="d1", template_id=template_id, name="X",
    )
    with pytest.raises(AcosError):
        await svc.suspend(emp.employee_id, company_id, expected_version=1)
