"""Skill 服务测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.capability.models import PromptAsset, Skill
from acos.capability.prompt_service import PromptAssetService
from acos.capability.skill_service import SkillService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def deps(tmp_path: Path) -> tuple[PromptAssetService, SkillService]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    return PromptAssetService(str(db_path)), SkillService(str(db_path))


async def _make_asset(svc: PromptAssetService, company_id: str = "comp-1") -> PromptAsset:
    return await svc.create(
        PromptAsset(company_id=company_id, name="base-prompt", segments={"s": "hi"})
    )


async def test_create_and_get_skill(deps: tuple[PromptAssetService, SkillService]) -> None:
    prompt_svc, skill_svc = deps
    asset = await _make_asset(prompt_svc)

    skill = Skill(
        company_id="comp-1",
        name="test-skill",
        prompt_asset_id=asset.prompt_asset_id,
        prompt_asset_version=asset.version,
        prompt_asset_checksum=asset.checksum,
    )
    created = await skill_svc.create(skill)
    assert created.name == "test-skill"
    assert created.version == 1
    assert created.checksum

    fetched = await skill_svc.get(created.skill_id)
    assert fetched is not None
    assert fetched.name == "test-skill"
    assert fetched.prompt_asset_id == asset.prompt_asset_id


async def test_cross_company_ref_denied(
    deps: tuple[PromptAssetService, SkillService],
) -> None:
    prompt_svc, skill_svc = deps
    asset_a = await _make_asset(prompt_svc, company_id="comp-A")

    skill = Skill(
        company_id="comp-B",
        name="bad-skill",
        prompt_asset_id=asset_a.prompt_asset_id,
        prompt_asset_version=1,
        prompt_asset_checksum=asset_a.checksum,
    )
    with pytest.raises(AcosError) as exc_info:
        await skill_svc.create(skill)
    assert exc_info.value.code == "ASSET-CROSS-COMPANY-REF-DENIED"


async def test_global_asset_allowed_cross_company(
    deps: tuple[PromptAssetService, SkillService],
) -> None:
    prompt_svc, skill_svc = deps
    global_asset = await prompt_svc.create(
        PromptAsset(company_scope="global", name="global-p", segments={"s": "g"})
    )
    skill = Skill(
        company_id="comp-A",
        name="global-ref-skill",
        prompt_asset_id=global_asset.prompt_asset_id,
        prompt_asset_version=1,
        prompt_asset_checksum=global_asset.checksum,
    )
    created = await skill_svc.create(skill)
    assert created.skill_id


async def test_nonexistent_asset_ref(deps: tuple[PromptAssetService, SkillService]) -> None:
    _, skill_svc = deps
    skill = Skill(
        company_id="comp-1",
        name="orphan-skill",
        prompt_asset_id="nonexistent",
        prompt_asset_version=1,
        prompt_asset_checksum="bad",
    )
    with pytest.raises(AcosError) as exc_info:
        await skill_svc.create(skill)
    assert exc_info.value.code == "CAP-VALIDATION"


async def test_save_draft_cas(deps: tuple[PromptAssetService, SkillService]) -> None:
    prompt_svc, skill_svc = deps
    asset = await _make_asset(prompt_svc)

    skill = Skill(
        company_id="comp-1",
        name="cas-test",
        prompt_asset_id=asset.prompt_asset_id,
        prompt_asset_version=1,
        prompt_asset_checksum=asset.checksum,
    )
    created = await skill_svc.create(skill)

    updated = await skill_svc.save_draft(created, expected_version=1)
    assert updated.version == 2

    with pytest.raises(AcosError) as exc_info:
        await skill_svc.save_draft(created, expected_version=1)
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_checksum_change_detection(
    deps: tuple[PromptAssetService, SkillService],
) -> None:
    prompt_svc, skill_svc = deps
    asset = await _make_asset(prompt_svc)

    skill = Skill(
        company_id="comp-1",
        name="cs-test",
        prompt_asset_id=asset.prompt_asset_id,
        prompt_asset_version=1,
        prompt_asset_checksum=asset.checksum,
    )
    created = await skill_svc.create(skill)
    old_checksum = created.checksum

    created.name = "cs-test-v2"
    updated = await skill_svc.save_draft(created, expected_version=1)
    assert updated.checksum != old_checksum


async def test_list_by_company(deps: tuple[PromptAssetService, SkillService]) -> None:
    prompt_svc, skill_svc = deps
    asset_a = await _make_asset(prompt_svc, company_id="comp-A")
    asset_b = await _make_asset(prompt_svc, company_id="comp-B")

    for i in range(2):
        await skill_svc.create(
            Skill(
                company_id="comp-A",
                name=f"skill-{i}",
                prompt_asset_id=asset_a.prompt_asset_id,
                prompt_asset_version=1,
                prompt_asset_checksum=asset_a.checksum,
            )
        )
    await skill_svc.create(
        Skill(
            company_id="comp-B",
            name="skill-b",
            prompt_asset_id=asset_b.prompt_asset_id,
            prompt_asset_version=1,
            prompt_asset_checksum=asset_b.checksum,
        )
    )

    a_skills = await skill_svc.list_by_company("comp-A")
    assert len(a_skills) == 2

    b_skills = await skill_svc.list_by_company("comp-B")
    assert len(b_skills) == 1


async def test_list_version_ordering(
    deps: tuple[PromptAssetService, SkillService],
) -> None:
    prompt_svc, skill_svc = deps
    asset = await _make_asset(prompt_svc)

    skill = Skill(
        company_id="comp-1",
        name="order-test",
        prompt_asset_id=asset.prompt_asset_id,
        prompt_asset_version=1,
        prompt_asset_checksum=asset.checksum,
    )
    created = await skill_svc.create(skill)
    await skill_svc.save_draft(created, expected_version=1)

    skills = await skill_svc.list_by_company("comp-1")
    versions = [s.version for s in skills]
    assert versions == sorted(versions, reverse=True)
