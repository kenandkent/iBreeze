"""员工排空测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.employee_drain_service import EmployeeDrainService
from acos.organization.service import OrganizationService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def setup(tmp_path: Path) -> tuple[EmployeeDrainService, str]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)
    return EmployeeDrainService(str(db_path)), company.company_id


async def test_start_drain_transfer(setup: tuple[EmployeeDrainService, str]) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id,
        employee_id="emp-1",
        operation="transfer",
        target_department_id="dept-new",
    )
    assert drain.drain_id
    assert drain.status == "active"
    assert drain.operation == "transfer"
    assert drain.target_department_id == "dept-new"


async def test_start_drain_suspend(setup: tuple[EmployeeDrainService, str]) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id,
        employee_id="emp-2",
        operation="suspend",
    )
    assert drain.operation == "suspend"
    assert drain.target_department_id is None


async def test_start_drain_archive(setup: tuple[EmployeeDrainService, str]) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id,
        employee_id="emp-3",
        operation="archive",
        timeout_seconds=300,
    )
    assert drain.operation == "archive"
    assert drain.timeout_seconds == 300


async def test_resolve_drain_completed(
    setup: tuple[EmployeeDrainService, str],
) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id, employee_id="emp-4",
        operation="transfer", target_department_id="dept-new",
    )
    resolved = await svc.resolve_drain(
        drain.drain_id, company_id,
        expected_status="active", result_status="completed",
    )
    assert resolved.status == "completed"


async def test_resolve_drain_failed(
    setup: tuple[EmployeeDrainService, str],
) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id, employee_id="emp-5",
        operation="suspend",
    )
    resolved = await svc.resolve_drain(
        drain.drain_id, company_id,
        expected_status="active", result_status="failed",
    )
    assert resolved.status == "failed"


async def test_resolve_drain_cas_conflict(
    setup: tuple[EmployeeDrainService, str],
) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id, employee_id="emp-6",
        operation="archive",
    )
    await svc.resolve_drain(
        drain.drain_id, company_id,
        expected_status="active", result_status="completed",
    )
    with pytest.raises(AcosError):
        await svc.resolve_drain(
            drain.drain_id, company_id,
            expected_status="active", result_status="failed",
        )


async def test_abort_drains_by_dissolution(
    setup: tuple[EmployeeDrainService, str],
) -> None:
    svc, company_id = setup
    await svc.start_drain(company_id=company_id, employee_id="emp-7", operation="transfer")
    await svc.start_drain(company_id=company_id, employee_id="emp-8", operation="suspend")
    count = await svc.abort_drains_by_dissolution(company_id)
    assert count == 2
    drains = await svc.list_by_employee(company_id, "emp-7")
    assert drains[0].status == "aborted_by_dissolution"


async def test_get_drain(setup: tuple[EmployeeDrainService, str]) -> None:
    svc, company_id = setup
    drain = await svc.start_drain(
        company_id=company_id, employee_id="emp-9", operation="transfer",
    )
    fetched = await svc.get(drain.drain_id)
    assert fetched is not None
    assert fetched.operation == "transfer"


async def test_get_nonexistent_drain(
    setup: tuple[EmployeeDrainService, str],
) -> None:
    svc, _ = setup
    result = await svc.get("nonexistent")
    assert result is None


async def test_list_by_employee_filter(
    setup: tuple[EmployeeDrainService, str],
) -> None:
    svc, company_id = setup
    d1 = await svc.start_drain(company_id=company_id, employee_id="emp-10", operation="transfer")
    await svc.start_drain(company_id=company_id, employee_id="emp-10", operation="suspend")
    await svc.resolve_drain(
        d1.drain_id, company_id,
        expected_status="active", result_status="completed",
    )
    active = await svc.list_by_employee(company_id, "emp-10", status="active")
    assert len(active) == 1
    completed = await svc.list_by_employee(company_id, "emp-10", status="completed")
    assert len(completed) == 1
    all_drains = await svc.list_by_employee(company_id, "emp-10")
    assert len(all_drains) == 2
