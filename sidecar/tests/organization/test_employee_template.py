"""员工模板测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.models import EmployeeTemplate
from acos.organization.service import OrganizationService
from acos.organization.template_service import TemplateService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def setup(tmp_path: Path) -> tuple[TemplateService, str]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)
    return TemplateService(str(db_path)), company.company_id


async def test_create_template(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-001",
        capability_version=1,
        default_role="开发者",
    )
    assert template.template_id
    assert template.status == "draft"
    assert template.capability_id == "cap-001"
    assert template.default_role == "开发者"
    assert template.version == 1
    assert template.company_id == company_id


async def test_get_template(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-002",
        capability_version=1,
        default_role="分析师",
    )
    fetched = await svc.get(template.template_id)
    assert fetched is not None
    assert fetched.capability_id == "cap-002"


async def test_get_nonexistent_template(setup: tuple[TemplateService, str]) -> None:
    svc, _ = setup
    result = await svc.get("nonexistent")
    assert result is None


async def test_save_draft_cas(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-old",
        capability_version=1,
        default_role="角色A",
    )
    updated = await svc.save_draft(
        template.template_id, company_id, expected_version=1,
        updates={"capability_id": "cap-new", "default_role": "角色B"},
    )
    assert updated.capability_id == "cap-new"
    assert updated.default_role == "角色B"
    assert updated.version == 2


async def test_save_draft_cas_conflict(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-x",
        capability_version=1,
        default_role="角色",
    )
    await svc.save_draft(
        template.template_id, company_id, expected_version=1,
        updates={"capability_id": "cap-y"},
    )
    with pytest.raises(AcosError) as exc_info:
        await svc.save_draft(
            template.template_id, company_id, expected_version=1,
            updates={"capability_id": "cap-z"},
        )
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_activate_template(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-003",
        capability_version=1,
        default_role="角色",
    )
    activated = await svc.activate(template.template_id, company_id, expected_version=1)
    assert activated.status == "active"
    assert activated.version == 2


async def test_archive_template(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-004",
        capability_version=1,
        default_role="角色",
    )
    await svc.activate(template.template_id, company_id, expected_version=1)
    archived = await svc.archive(template.template_id, company_id, expected_version=2)
    assert archived.status == "archived"
    assert archived.version == 3


async def test_activate_draft_only(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-005",
        capability_version=1,
        default_role="角色",
    )
    await svc.activate(template.template_id, company_id, expected_version=1)
    with pytest.raises(AcosError):
        await svc.activate(template.template_id, company_id, expected_version=2)


async def test_archive_active_only(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id="cap-006",
        capability_version=1,
        default_role="角色",
    )
    with pytest.raises(AcosError):
        await svc.archive(template.template_id, company_id, expected_version=1)


async def test_list_by_company(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    await svc.create(company_id=company_id, capability_id="c1", capability_version=1, default_role="r1")
    await svc.create(company_id=company_id, capability_id="c2", capability_version=1, default_role="r2")
    templates = await svc.list_by_company(company_id)
    assert len(templates) == 2


async def test_list_by_company_with_status_filter(setup: tuple[TemplateService, str]) -> None:
    svc, company_id = setup
    t1 = await svc.create(company_id=company_id, capability_id="c1", capability_version=1, default_role="r1")
    await svc.create(company_id=company_id, capability_id="c2", capability_version=1, default_role="r2")
    await svc.activate(t1.template_id, company_id, expected_version=1)
    active = await svc.list_by_company(company_id, status="active")
    assert len(active) == 1
    draft = await svc.list_by_company(company_id, status="draft")
    assert len(draft) == 1
