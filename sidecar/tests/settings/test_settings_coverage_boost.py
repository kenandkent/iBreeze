"""settings.* 覆盖率补充测试：company / knowledgePolicy / security /
workspace / notification 五类策略的 get/update 校验分支（缺参、not found、
CAS 冲突、consent、字段更新）。

仅测试，不改业务代码。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.service import OrganizationService
from acos.rpc.errors import AcosError
from acos.rpc.methods_settings import SettingsMethods
from acos.store.migrator import Migrator

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = str(tmp_path / "test.db")
    migrator = Migrator(p)
    await migrator.run_pending_migrations(MIGRATIONS_DIR)
    return p


@pytest.fixture
async def company_id(db_path: str) -> str:
    svc = OrganizationService(db_path)
    company = await svc.create_company("覆盖测试公司", "owner-1")
    return company.company_id


@pytest.fixture
def sm(db_path: str) -> SettingsMethods:
    return SettingsMethods(db_path)


# ── register_to ─────────────────────────────────────────

def test_register_to_registers_all(sm: SettingsMethods) -> None:
    registered: dict[str, object] = {}

    class _Server:
        def register_method(self, name, fn):
            registered[name] = fn

    sm.register_to(_Server())
    for name in (
        "settings.company.get", "settings.company.update",
        "settings.knowledgePolicy.get", "settings.knowledgePolicy.update",
        "settings.securityPolicy.get", "settings.securityPolicy.update",
        "settings.workspacePolicy.get", "settings.workspacePolicy.update",
        "settings.notification.get", "settings.notification.update",
    ):
        assert name in registered


# ── company ─────────────────────────────────────────────

async def test_company_get_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._company_get({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_company_get_not_found(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._company_get({"company_id": "no-such"})
    assert exc.value.code == "ORG-NOT-FOUND"


async def test_company_get_returns_policies(sm: SettingsMethods, company_id: str) -> None:
    r = await sm._company_get({"company_id": company_id})
    assert isinstance(r["default_provider_policy"], dict)
    assert isinstance(r["default_budget_policy"], dict)


async def test_company_update_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._company_update({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_company_update_name(sm: SettingsMethods, company_id: str) -> None:
    r = await sm._company_update(
        {"company_id": company_id, "expected_version": 1, "name": "新名"}
    )
    assert r["version"] == 2


# ── knowledge policy ────────────────────────────────────

async def test_knowledge_get_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._knowledge_get({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_knowledge_get_returns_config(sm: SettingsMethods, company_id: str) -> None:
    r = await sm._knowledge_get({"company_id": company_id})
    assert r["version"] == 1
    assert "config" in r


async def test_knowledge_update_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._knowledge_update({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_knowledge_update_missing_version(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._knowledge_update({"company_id": company_id, "config": {}})
    assert exc.value.code == "ORG-VALIDATION"


async def test_knowledge_update_missing_config(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._knowledge_update(
            {"company_id": company_id, "expected_policy_version": 1}
        )
    assert exc.value.code == "ORG-VALIDATION"


async def test_knowledge_update_local_ok(sm: SettingsMethods, company_id: str) -> None:
    config = {
        "extraction_provider_id": "p1", "extraction_model": "m1",
        "extraction_mode": "local", "fallback_mode": "pause",
        "allow_cloud": False, "consent": None,
    }
    r = await sm._knowledge_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert r["version"] == 2


async def test_knowledge_update_cas_conflict(sm: SettingsMethods, company_id: str) -> None:
    config = {
        "extraction_provider_id": "p1", "extraction_model": "m1",
        "extraction_mode": "local", "fallback_mode": "pause",
        "allow_cloud": False, "consent": None,
    }
    await sm._knowledge_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    with pytest.raises(AcosError) as exc:
        await sm._knowledge_update(
            {"company_id": company_id, "expected_policy_version": 1, "config": config}
        )
    assert exc.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


# ── security policy ─────────────────────────────────────

async def test_security_get_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._security_get({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_security_get_returns_config(sm: SettingsMethods, company_id: str) -> None:
    r = await sm._security_get({"company_id": company_id})
    assert r["version"] == 1


async def test_security_update_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._security_update({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_security_update_missing_version(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._security_update({"company_id": company_id, "config": {}})
    assert exc.value.code == "ORG-VALIDATION"


async def test_security_update_missing_config(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._security_update(
            {"company_id": company_id, "expected_policy_version": 1}
        )
    assert exc.value.code == "ORG-VALIDATION"


async def test_security_update_fields(sm: SettingsMethods, company_id: str) -> None:
    config = {"inherit_tool_bindings": False, "allowed_commands": ["ls"]}
    r = await sm._security_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert r["version"] == 2
    assert r["config"]["allowed_commands"] == ["ls"]


# ── workspace policy ────────────────────────────────────

async def test_workspace_get_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._workspace_get({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_workspace_get_returns_config(sm: SettingsMethods, company_id: str) -> None:
    r = await sm._workspace_get({"company_id": company_id})
    assert r["version"] == 1


async def test_workspace_update_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._workspace_update({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_workspace_update_missing_version(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._workspace_update({"company_id": company_id, "config": {}})
    assert exc.value.code == "ORG-VALIDATION"


async def test_workspace_update_missing_config(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._workspace_update(
            {"company_id": company_id, "expected_policy_version": 1}
        )
    assert exc.value.code == "ORG-VALIDATION"


async def test_workspace_update_cas_conflict(sm: SettingsMethods, company_id: str) -> None:
    config = {"root_path": "/data", "allowed_types": ["code"]}
    await sm._workspace_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    with pytest.raises(AcosError) as exc:
        await sm._workspace_update(
            {"company_id": company_id, "expected_policy_version": 1, "config": config}
        )
    assert exc.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


# ── notification policy ─────────────────────────────────

async def test_notification_get_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._notification_get({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_notification_get_returns_config(sm: SettingsMethods, company_id: str) -> None:
    r = await sm._notification_get({"company_id": company_id})
    assert r["version"] == 1


async def test_notification_update_missing_id(sm: SettingsMethods) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._notification_update({})
    assert exc.value.code == "ORG-VALIDATION"


async def test_notification_update_missing_version(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._notification_update({"company_id": company_id, "config": {}})
    assert exc.value.code == "ORG-VALIDATION"


async def test_notification_update_missing_config(sm: SettingsMethods, company_id: str) -> None:
    with pytest.raises(AcosError) as exc:
        await sm._notification_update(
            {"company_id": company_id, "expected_policy_version": 1}
        )
    assert exc.value.code == "ORG-VALIDATION"


async def test_notification_update_fields(sm: SettingsMethods, company_id: str) -> None:
    config = {"email_enabled": False, "channels": ["in_app", "email"]}
    r = await sm._notification_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert r["version"] == 2
    assert r["config"]["channels"] == ["in_app", "email"]
