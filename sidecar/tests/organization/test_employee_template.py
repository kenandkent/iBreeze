"""员工模板测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.capability.models import Capability, PromptAsset, Skill
from acos.capability.prompt_service import PromptAssetService
from acos.capability.skill_service import SkillService
from acos.capability.service import CapabilityService
from acos.capability.versioning import VersioningService
from acos.organization.models import EmployeeTemplate
from acos.organization.service import OrganizationService
from acos.organization.template_service import TemplateService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


async def _publish_prompt_asset(prompt_svc: PromptAssetService, versioning: VersioningService, company_id: str, name: str) -> tuple[str, int]:
    """创建并发布一个 PromptAsset，返回 (prompt_asset_id, version)"""
    prompt = PromptAsset(
        company_scope="company",
        company_id=company_id,
        name=name,
        segments={
            "system": "你是助手",
            "developer": "",
            "user_template": "{{input}}",
            "tool_instructions": "",
            "output_contract": "",
        },
        variables=[],
        context_slots=[],
    )
    prompt = await prompt_svc.create(prompt)
    await versioning.submit_review("prompt_asset", prompt.prompt_asset_id, 1)
    await versioning.publish("prompt_asset", prompt.prompt_asset_id, 1)
    return prompt.prompt_asset_id, 1


async def _publish_skill(skill_svc: SkillService, versioning: VersioningService, company_id: str, prompt_asset_id: str, name: str) -> str:
    """创建并发布一个 Skill，返回 skill_id"""
    skill = Skill(
        company_scope="company",
        company_id=company_id,
        name=name,
        prompt_asset_id=prompt_asset_id,
        prompt_asset_version=1,
        tool_bindings=[],
        knowledge_refs=[],
        input_schema={},
        output_schema={},
    )
    skill = await skill_svc.create(skill)
    await versioning.submit_review("skill", skill.skill_id, 1)
    await versioning.publish("skill", skill.skill_id, 1)
    return skill.skill_id


async def _publish_capability(cap_svc: CapabilityService, versioning: VersioningService, company_id: str, skill_id: str, name: str) -> str:
    """创建并发布一个 Capability，返回 capability_id"""
    # 先获取 skill 的 checksum
    import aiosqlite
    async with aiosqlite.connect(cap_svc._db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT checksum FROM skills WHERE skill_id = ?",
            (skill_id,),
        )
        skill_row = await cursor.fetchone()
        skill_checksum = skill_row["checksum"] if skill_row else ""

    cap = Capability(
        company_id=company_id,
        name=name,
        description=f"{name} 描述",
        source_category="code",
        visibility="company",
        cost_policy={"stability_level": 5},
    )
    cap = await cap_svc.create(
        cap,
        bindings=[{"skill_id": skill_id, "skill_version": 1, "skill_version_checksum": skill_checksum}],
    )
    await versioning.submit_review("capability", cap.capability_id, 1)
    await versioning.publish("capability", cap.capability_id, 1)
    return cap.capability_id


@pytest.fixture
async def setup(tmp_path: Path) -> tuple[TemplateService, str, str]:
    """返回 (template_svc, company_id, capability_id)"""
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    org_svc = OrganizationService(str(db_path))
    company = await org_svc.create_company("测试公司", "owner-1")
    await org_svc.activate_company(company.company_id, expected_version=1)

    # 创建完整的 capability 链：PromptAsset -> Skill -> Capability
    prompt_svc = PromptAssetService(str(db_path))
    skill_svc = SkillService(str(db_path))
    cap_svc = CapabilityService(str(db_path))
    versioning = VersioningService(str(db_path))

    prompt_asset_id, _ = await _publish_prompt_asset(prompt_svc, versioning, company.company_id, "测试Prompt")
    skill_id = await _publish_skill(skill_svc, versioning, company.company_id, prompt_asset_id, "测试Skill")
    capability_id = await _publish_capability(cap_svc, versioning, company.company_id, skill_id, "测试能力")

    template_svc = TemplateService(str(db_path))
    return template_svc, company.company_id, capability_id


async def test_create_template(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="开发者",
    )
    assert template.template_id
    assert template.status == "draft"
    assert template.capability_id == capability_id
    assert template.default_role == "开发者"
    assert template.version == 1
    assert template.company_id == company_id
    # capability_snapshot 应该已生成
    assert template.capability_snapshot
    assert "snapshot_id" in template.capability_snapshot


async def test_get_template(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="分析师",
    )
    fetched = await svc.get(template.template_id)
    assert fetched is not None
    assert fetched.capability_id == capability_id


async def test_get_nonexistent_template(setup: tuple[TemplateService, str, str]) -> None:
    svc, _, _ = setup
    result = await svc.get("nonexistent")
    assert result is None


async def test_save_draft_cas(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="角色A",
    )
    # 创建另一个 capability 用于更新
    cap_svc = CapabilityService(svc._db_path)
    ver_svc = VersioningService(svc._db_path)
    prompt_asset_id, _ = await _publish_prompt_asset(PromptAssetService(svc._db_path), ver_svc, company_id, "新Prompt")
    skill_id = await _publish_skill(SkillService(svc._db_path), ver_svc, company_id, prompt_asset_id, "新Skill")
    new_cap_id = await _publish_capability(cap_svc, ver_svc, company_id, skill_id, "新能力")
    updated = await svc.save_draft(
        template.template_id, company_id, expected_version=1,
        updates={"capability_id": new_cap_id, "default_role": "角色B"},
    )
    assert updated.capability_id == new_cap_id
    assert updated.default_role == "角色B"
    assert updated.version == 2


async def test_save_draft_cas_conflict(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="角色",
    )
    cap_svc = CapabilityService(svc._db_path)
    ver_svc = VersioningService(svc._db_path)
    prompt_asset_id, _ = await _publish_prompt_asset(PromptAssetService(svc._db_path), ver_svc, company_id, "新Prompt")
    skill_id = await _publish_skill(SkillService(svc._db_path), ver_svc, company_id, prompt_asset_id, "新Skill")
    new_cap_id = await _publish_capability(cap_svc, ver_svc, company_id, skill_id, "新能力")
    await svc.save_draft(
        template.template_id, company_id, expected_version=1,
        updates={"capability_id": new_cap_id},
    )
    prompt_asset_id2, _ = await _publish_prompt_asset(PromptAssetService(svc._db_path), ver_svc, company_id, "另一个Prompt")
    skill_id2 = await _publish_skill(SkillService(svc._db_path), ver_svc, company_id, prompt_asset_id2, "另一个Skill")
    new_cap_id2 = await _publish_capability(cap_svc, ver_svc, company_id, skill_id2, "另一个能力")
    with pytest.raises(AcosError) as exc_info:
        await svc.save_draft(
            template.template_id, company_id, expected_version=1,
            updates={"capability_id": new_cap_id2},
        )
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_activate_template(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="角色",
    )
    activated = await svc.activate(template.template_id, company_id, expected_version=1)
    assert activated.status == "active"
    assert activated.version == 2


async def test_archive_template(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="角色",
    )
    await svc.activate(template.template_id, company_id, expected_version=1)
    archived = await svc.archive(template.template_id, company_id, expected_version=2)
    assert archived.status == "archived"
    assert archived.version == 3


async def test_activate_draft_only(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="角色",
    )
    await svc.activate(template.template_id, company_id, expected_version=1)
    with pytest.raises(AcosError):
        await svc.activate(template.template_id, company_id, expected_version=2)


async def test_archive_active_only(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    template = await svc.create(
        company_id=company_id,
        capability_id=capability_id,
        capability_version=1,
        default_role="角色",
    )
    with pytest.raises(AcosError):
        await svc.archive(template.template_id, company_id, expected_version=1)


async def test_list_by_company(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    cap_svc = CapabilityService(svc._db_path)
    ver_svc = VersioningService(svc._db_path)
    prompt_asset_id, _ = await _publish_prompt_asset(PromptAssetService(svc._db_path), ver_svc, company_id, "Prompt2")
    skill_id = await _publish_skill(SkillService(svc._db_path), ver_svc, company_id, prompt_asset_id, "Skill2")
    cap2_id = await _publish_capability(cap_svc, ver_svc, company_id, skill_id, "能力2")
    await svc.create(company_id=company_id, capability_id=capability_id, capability_version=1, default_role="r1")
    await svc.create(company_id=company_id, capability_id=cap2_id, capability_version=1, default_role="r2")
    templates = await svc.list_by_company(company_id)
    assert len(templates) == 2


async def test_list_by_company_with_status_filter(setup: tuple[TemplateService, str, str]) -> None:
    svc, company_id, capability_id = setup
    cap_svc = CapabilityService(svc._db_path)
    ver_svc = VersioningService(svc._db_path)
    prompt_asset_id, _ = await _publish_prompt_asset(PromptAssetService(svc._db_path), ver_svc, company_id, "Prompt2")
    skill_id = await _publish_skill(SkillService(svc._db_path), ver_svc, company_id, prompt_asset_id, "Skill2")
    cap2_id = await _publish_capability(cap_svc, ver_svc, company_id, skill_id, "能力2")
    t1 = await svc.create(company_id=company_id, capability_id=capability_id, capability_version=1, default_role="r1")
    await svc.create(company_id=company_id, capability_id=cap2_id, capability_version=1, default_role="r2")
    await svc.activate(t1.template_id, company_id, expected_version=1)
    active = await svc.list_by_company(company_id, status="active")
    assert len(active) == 1
    draft = await svc.list_by_company(company_id, status="draft")
    assert len(draft) == 1