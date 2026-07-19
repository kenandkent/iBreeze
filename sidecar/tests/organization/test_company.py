"""Company 模型测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.models import Company
from acos.organization.service import OrganizationService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def svc(tmp_path: Path) -> OrganizationService:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    return OrganizationService(str(db_path))


async def test_create_company(svc: OrganizationService) -> Company:
    company = await svc.create_company("测试公司", "owner-1")
    assert company.name == "测试公司"
    assert company.status == "initializing"
    assert company.company_id
    assert company.root_department_id
    assert company.version == 1

    fetched = await svc.get_company(company.company_id)
    assert fetched is not None
    assert fetched.name == "测试公司"
    return company


async def test_company_status_transitions(svc: OrganizationService) -> None:
    company = await svc.create_company("状态测试", "owner-1")

    activated = await svc.activate_company(company.company_id, expected_version=1)
    assert activated.status == "active"

    dissolving = await svc.start_dissolution(
        activated.company_id, expected_version=2, operator="owner-1"
    )
    assert dissolving.status == "dissolving"

    dissolved = await svc.complete_dissolution(dissolving.company_id)
    assert dissolved.status == "dissolved"


async def test_company_cas_conflict(svc: OrganizationService) -> None:
    company = await svc.create_company("CAS测试", "owner-1")

    await svc.update_company(company.company_id, expected_version=1, updates={"name": "新名字"})

    with pytest.raises(AcosError) as exc_info:
        await svc.update_company(
            company.company_id, expected_version=1, updates={"name": "冲突名字"}
        )
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_company_dissolution(svc: OrganizationService) -> None:
    company = await svc.create_company("解散测试", "owner-1")
    activated = await svc.activate_company(company.company_id, expected_version=1)
    dissolving = await svc.start_dissolution(
        activated.company_id, expected_version=2, operator="owner-1"
    )
    dissolved = await svc.complete_dissolution(dissolving.company_id)

    assert dissolved.status == "dissolved"
    fetched = await svc.get_company(dissolved.company_id)
    assert fetched is not None
    assert fetched.status == "dissolved"


async def test_dissolved_company_rejects_writes(svc: OrganizationService) -> None:
    company = await svc.create_company("拒绝写入测试", "owner-1")
    activated = await svc.activate_company(company.company_id, expected_version=1)
    dissolving = await svc.start_dissolution(
        activated.company_id, expected_version=2, operator="owner-1"
    )
    await svc.complete_dissolution(dissolving.company_id)

    with pytest.raises(AcosError) as exc_info:
        await svc.update_company(
            company.company_id, expected_version=4, updates={"name": "不应成功"}
        )
    assert exc_info.value.code == "ORG-COMPANY-DISSOLVED"


async def test_update_company_name(svc: OrganizationService) -> None:
    company = await svc.create_company("原名", "owner-1")
    updated = await svc.update_company(
        company.company_id, expected_version=1, updates={"name": "新名"}
    )
    assert updated.name == "新名"
    assert updated.version == 2


async def test_get_nonexistent_company(svc: OrganizationService) -> None:
    result = await svc.get_company("nonexistent")
    assert result is None


async def test_activate_wrong_status_fails(svc: OrganizationService) -> None:
    company = await svc.create_company("错误激活", "owner-1")
    await svc.activate_company(company.company_id, expected_version=1)

    with pytest.raises(AcosError):
        await svc.activate_company(company.company_id, expected_version=2)


async def test_create_company_default_policies(svc: OrganizationService) -> None:
    company = await svc.create_company("策略测试", "owner-1")
    fetched = await svc.get_company(company.company_id)
    assert fetched is not None
    # 默认策略：provider policy 含 free/standard/premium 槽位
    assert "free" in fetched.default_provider_policy
    assert "standard" in fetched.default_provider_policy
    assert "premium" in fetched.default_provider_policy
    # 默认预算策略：含 currency 和 default_on_budget_exceeded
    assert fetched.default_budget_policy.get("currency") == "CNY"
    assert fetched.default_budget_policy.get("default_on_budget_exceeded") == "require_approval"
