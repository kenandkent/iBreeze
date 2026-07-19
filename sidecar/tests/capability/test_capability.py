"""Capability 服务测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.capability.models import Capability, PromptAsset, Skill
from acos.capability.prompt_service import PromptAssetService
from acos.capability.service import CapabilityService
from acos.capability.skill_service import SkillService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def deps(tmp_path: Path) -> tuple[PromptAssetService, SkillService, CapabilityService]:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    return (
        PromptAssetService(str(db_path)),
        SkillService(str(db_path)),
        CapabilityService(str(db_path)),
    )


async def _make_skill(
    prompt_svc: PromptAssetService,
    skill_svc: SkillService,
    company_id: str = "comp-1",
    name: str = "base-skill",
) -> Skill:
    asset = await prompt_svc.create(
        PromptAsset(company_id=company_id, name=f"prompt-{name}", segments={"s": "hi"})
    )
    return await skill_svc.create(
        Skill(
            company_id=company_id,
            name=name,
            prompt_asset_id=asset.prompt_asset_id,
            prompt_asset_version=1,
            prompt_asset_checksum=asset.checksum,
        )
    )


async def test_create_and_get_capability(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    prompt_svc, skill_svc, cap_svc = deps
    skill = await _make_skill(prompt_svc, skill_svc)

    cap = Capability(
        company_id="comp-1",
        name="test-cap",
        description="A test capability",
        cost_policy={"stability_level": 5},
    )
    bindings = [
        {
            "skill_id": skill.skill_id,
            "skill_version": 1,
            "skill_version_checksum": skill.checksum,
        }
    ]
    created = await cap_svc.create(cap, bindings)
    assert created.name == "test-cap"
    assert created.version == 1
    assert created.checksum
    assert created.cost_policy == {"stability_level": 5}

    fetched = await cap_svc.get(created.capability_id)
    assert fetched is not None
    assert fetched.name == "test-cap"


async def test_get_bindings(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    prompt_svc, skill_svc, cap_svc = deps
    skill1 = await _make_skill(prompt_svc, skill_svc, name="skill-1")
    skill2 = await _make_skill(prompt_svc, skill_svc, name="skill-2")

    cap = Capability(company_id="comp-1", name="multi-skill-cap")
    bindings = [
        {
            "skill_id": skill1.skill_id,
            "skill_version": 1,
            "skill_version_checksum": skill1.checksum,
        },
        {
            "skill_id": skill2.skill_id,
            "skill_version": 1,
            "skill_version_checksum": skill2.checksum,
        },
    ]
    created = await cap_svc.create(cap, bindings)

    got_bindings = await cap_svc.get_bindings(created.capability_id, 1)
    assert len(got_bindings) == 2
    assert got_bindings[0]["ordinal"] == 1
    assert got_bindings[1]["ordinal"] == 2


async def test_invalid_stability_level(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    _, _, cap_svc = deps

    cap = Capability(
        company_id="comp-1",
        name="bad-cap",
        cost_policy={"stability_level": 11},
    )
    with pytest.raises(AcosError) as exc_info:
        await cap_svc.create(cap)
    assert exc_info.value.code == "CAP-VALIDATION"


async def test_stability_level_zero(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    _, _, cap_svc = deps

    cap = Capability(
        company_id="comp-1",
        name="bad-cap",
        cost_policy={"stability_level": 0},
    )
    with pytest.raises(AcosError) as exc_info:
        await cap_svc.create(cap)
    assert exc_info.value.code == "CAP-VALIDATION"


async def test_cross_company_skill_ref_denied(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    prompt_svc, skill_svc, cap_svc = deps
    skill_b = await _make_skill(prompt_svc, skill_svc, company_id="comp-B")

    cap = Capability(company_id="comp-A", name="cross-ref")
    bindings = [{"skill_id": skill_b.skill_id, "skill_version": 1, "skill_version_checksum": ""}]
    with pytest.raises(AcosError) as exc_info:
        await cap_svc.create(cap, bindings)
    assert exc_info.value.code == "ASSET-CROSS-COMPANY-REF-DENIED"


async def test_nonexistent_skill_ref(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    _, _, cap_svc = deps

    cap = Capability(company_id="comp-1", name="orphan-cap")
    bindings = [{"skill_id": "nonexistent", "skill_version": 1, "skill_version_checksum": ""}]
    with pytest.raises(AcosError) as exc_info:
        await cap_svc.create(cap, bindings)
    assert exc_info.value.code == "CAP-VALIDATION"


async def test_save_draft_cas(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    prompt_svc, skill_svc, cap_svc = deps
    skill = await _make_skill(prompt_svc, skill_svc)

    cap = Capability(
        company_id="comp-1",
        name="cas-cap",
        cost_policy={"stability_level": 3},
    )
    bindings = [
        {
            "skill_id": skill.skill_id,
            "skill_version": 1,
            "skill_version_checksum": skill.checksum,
        }
    ]
    created = await cap_svc.create(cap, bindings)

    updated = await cap_svc.save_draft(
        created, expected_version=1, bindings=bindings
    )
    assert updated.version == 2

    with pytest.raises(AcosError) as exc_info:
        await cap_svc.save_draft(created, expected_version=1)
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_list_by_company(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    prompt_svc, skill_svc, cap_svc = deps
    skill_a = await _make_skill(prompt_svc, skill_svc, company_id="comp-A", name="skill-a")
    skill_b = await _make_skill(prompt_svc, skill_svc, company_id="comp-B", name="skill-b")

    for i in range(2):
        cap = Capability(company_id="comp-A", name=f"cap-{i}")
        bindings = [
            {
                "skill_id": skill_a.skill_id,
                "skill_version": 1,
                "skill_version_checksum": skill_a.checksum,
            }
        ]
        await cap_svc.create(cap, bindings)

    cap_b = Capability(company_id="comp-B", name="cap-b")
    bindings_b = [
        {
            "skill_id": skill_b.skill_id,
            "skill_version": 1,
            "skill_version_checksum": skill_b.checksum,
        }
    ]
    await cap_svc.create(cap_b, bindings_b)

    a_caps = await cap_svc.list_by_company("comp-A")
    assert len(a_caps) == 2


async def test_version_list_ordering(
    deps: tuple[PromptAssetService, SkillService, CapabilityService],
) -> None:
    prompt_svc, skill_svc, cap_svc = deps
    skill = await _make_skill(prompt_svc, skill_svc)

    cap = Capability(company_id="comp-1", name="order-cap")
    bindings = [
        {
            "skill_id": skill.skill_id,
            "skill_version": 1,
            "skill_version_checksum": skill.checksum,
        }
    ]
    created = await cap_svc.create(cap, bindings)
    await cap_svc.save_draft(created, expected_version=1, bindings=bindings)

    caps = await cap_svc.list_by_company("comp-1")
    versions = [c.version for c in caps]
    assert versions == sorted(versions, reverse=True)
