"""访问授权测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.permission_engine import PermissionEngine
from acos.organization.service import OrganizationService
from acos.store.migrator import Migrator


@pytest.fixture
async def setup(tmp_path: Path) -> tuple[PermissionEngine, str]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)
    return PermissionEngine(str(db_path)), company.company_id


async def test_grant_department_read(setup: tuple[PermissionEngine, str]) -> None:
    engine, company_id = setup
    grant_id = await engine.grant(
        company_id=company_id, employee_id="emp-1",
        target_type="department", target_id="dept-1",
        permission="department_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    assert grant_id
    assert (await engine.authorize("emp-1", company_id, "department", "dept-1"))["decision"] == "allow"


async def test_grant_task_read(setup: tuple[PermissionEngine, str]) -> None:
    engine, company_id = setup
    grant_id = await engine.grant(
        company_id=company_id, employee_id="emp-2",
        target_type="task", target_id="task-1",
        permission="task_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    assert grant_id
    assert (await engine.authorize("emp-2", company_id, "task", "task-1"))["decision"] == "allow"
    assert (await engine.authorize("emp-2", company_id, "department", "dept-1"))["decision"] == "deny"


async def test_revoke(setup: tuple[PermissionEngine, str]) -> None:
    engine, company_id = setup
    grant_id = await engine.grant(
        company_id=company_id, employee_id="emp-3",
        target_type="department", target_id="dept-2",
        permission="department_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    assert (await engine.authorize("emp-3", company_id, "department", "dept-2"))["decision"] == "allow"
    revoked = await engine.revoke(grant_id, company_id, expected_version=1)
    assert revoked
    assert (await engine.authorize("emp-3", company_id, "department", "dept-2"))["decision"] == "deny"


async def test_revoke_wrong_version(setup: tuple[PermissionEngine, str]) -> None:
    engine, company_id = setup
    grant_id = await engine.grant(
        company_id=company_id, employee_id="emp-4",
        target_type="department", target_id="dept-3",
        permission="department_read", expires_at="2099-01-01T00:00:00Z",
        approved_by="owner-1",
    )
    result = await engine.revoke(grant_id, company_id, expected_version=99)
    assert result is False


async def test_scope_hash_deterministic(
    setup: tuple[PermissionEngine, str],
) -> None:
    engine, company_id = setup
    scope1 = await engine.compute_scope("emp-x", company_id)
    scope2 = await engine.compute_scope("emp-x", company_id)
    assert scope1["scope_hash"] == scope2["scope_hash"]


async def test_authorize_unknown_resource_type(
    setup: tuple[PermissionEngine, str],
) -> None:
    engine, company_id = setup
    result = await engine.authorize("emp-1", company_id, "unknown", "id-1")
    assert result["decision"] == "deny"
