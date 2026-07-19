"""Settings RPC 测试：覆盖公司设置、各版本化策略 get/update 的 CAS、
并发冲突与 knowledge policy 云端 consent 校验。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.organization.service import OrganizationService
from acos.rpc.errors import AcosError
from acos.rpc.methods_settings import SettingsMethods
from acos.rpc.methods_sys import SysMethods
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
    company = await svc.create_company("设置测试公司", "owner-1")
    return company.company_id


@pytest.fixture
def settings_methods(db_path: str) -> SettingsMethods:
    return SettingsMethods(db_path)


# ── company ────────────────────────────────────────────────


async def test_company_get(settings_methods: SettingsMethods, company_id: str) -> None:
    result = await settings_methods._company_get({"company_id": company_id})
    assert result["company_id"] == company_id
    assert result["name"] == "设置测试公司"
    assert result["version"] == 1


async def test_company_update_cas(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    r1 = await settings_methods._company_update(
        {"company_id": company_id, "expected_version": 1, "name": "改名A"}
    )
    assert r1["version"] == 2
    # 旧版本冲突
    with pytest.raises(AcosError) as exc:
        await settings_methods._company_update(
            {"company_id": company_id, "expected_version": 1, "name": "改名B"}
        )
    assert exc.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"
    # 新版本成功
    r2 = await settings_methods._company_update(
        {"company_id": company_id, "expected_version": 2, "name": "改名C"}
    )
    assert r2["version"] == 3


# ── knowledge policy ───────────────────────────────────────


async def test_knowledge_policy_get(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    result = await settings_methods._knowledge_get({"company_id": company_id})
    assert result["company_id"] == company_id
    assert result["version"] == 1
    assert "config" in result


async def test_knowledge_policy_update_cas(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    config = {
        "extraction_provider_id": "p1",
        "extraction_model": "m1",
        "extraction_mode": "local",
        "fallback_mode": "pause",
        "allow_cloud": False,
        "consent": None,
    }
    r1 = await settings_methods._knowledge_update(
        {
            "company_id": company_id,
            "expected_policy_version": 1,
            "config": config,
        }
    )
    assert r1["version"] == 2
    # 旧版本冲突
    with pytest.raises(AcosError) as exc:
        await settings_methods._knowledge_update(
            {
                "company_id": company_id,
                "expected_policy_version": 1,
                "config": config,
            }
        )
    assert exc.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"
    # 新版本成功
    r2 = await settings_methods._knowledge_update(
        {
            "company_id": company_id,
            "expected_policy_version": 2,
            "config": config,
        }
    )
    assert r2["version"] == 3


async def test_knowledge_policy_cloud_requires_consent(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    config = {
        "extraction_provider_id": "p1",
        "extraction_model": "m1",
        "extraction_mode": "cloud",
        "fallback_mode": "pause",
        "allow_cloud": True,
        "consent": None,
    }
    # 缺少 consent → 拒绝
    with pytest.raises(AcosError) as exc:
        await settings_methods._knowledge_update(
            {"company_id": company_id, "expected_policy_version": 1, "config": config}
        )
    assert exc.value.code == "KG-CLOUD-CONSENT-REQUIRED"


async def test_knowledge_policy_cloud_with_consent(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    config = {
        "extraction_provider_id": "p1",
        "extraction_model": "m1",
        "extraction_mode": "cloud",
        "fallback_mode": "pause",
        "allow_cloud": True,
        "consent": {"consented_by": "owner-1", "note": "agree"},
    }
    result = await settings_methods._knowledge_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert result["version"] == 2
    # 服务端注入 consent_version / consented_at
    assert result["config"]["consent"]["consent_version"] == 2
    assert result["config"]["consent"]["consented_at"]


async def test_knowledge_policy_revoke_cloud_clears_consent(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    cloud_config = {
        "extraction_provider_id": "p1",
        "extraction_model": "m1",
        "extraction_mode": "cloud",
        "fallback_mode": "pause",
        "allow_cloud": True,
        "consent": {"consented_by": "owner-1"},
    }
    v2 = await settings_methods._knowledge_update(
        {
            "company_id": company_id,
            "expected_policy_version": 1,
            "config": cloud_config,
        }
    )
    local_config = {
        "extraction_provider_id": "p1",
        "extraction_model": "m1",
        "extraction_mode": "local",
        "fallback_mode": "pause",
        "allow_cloud": False,
        "consent": {"consented_by": "owner-1"},
    }
    v3 = await settings_methods._knowledge_update(
        {
            "company_id": company_id,
            "expected_policy_version": v2["version"],
            "config": local_config,
        }
    )
    # 撤回云端 → consent 被清空
    assert v3["config"]["consent"] is None


# ── security / workspace / notification policy ─────────────


async def test_security_policy_cas(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    config = {"inherit_tool_bindings": True, "allowed_commands": ["run"]}
    r1 = await settings_methods._security_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert r1["version"] == 2
    with pytest.raises(AcosError) as exc:
        await settings_methods._security_update(
            {
                "company_id": company_id,
                "expected_policy_version": 1,
                "config": config,
            }
        )
    assert exc.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_workspace_policy_cas(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    config = {"root_path": "/data", "allowed_types": ["code"]}
    r1 = await settings_methods._workspace_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert r1["version"] == 2
    assert r1["config"]["root_path"] == "/data"
    get = await settings_methods._workspace_get({"company_id": company_id})
    assert get["version"] == 2


async def test_notification_policy_cas(
    settings_methods: SettingsMethods, company_id: str
) -> None:
    config = {"email_enabled": True, "channels": ["in_app"]}
    r1 = await settings_methods._notification_update(
        {"company_id": company_id, "expected_policy_version": 1, "config": config}
    )
    assert r1["version"] == 2
    get = await settings_methods._notification_get({"company_id": company_id})
    assert get["config"]["email_enabled"] is True
