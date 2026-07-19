"""PromptAsset 服务测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.capability.models import PromptAsset
from acos.capability.prompt_service import PromptAssetService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def svc(tmp_path: Path) -> PromptAssetService:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    return PromptAssetService(str(db_path))


async def test_create_and_get(svc: PromptAssetService) -> None:
    asset = PromptAsset(
        company_id="comp-1",
        name="test-prompt",
        segments={"system": "You are helpful."},
        variables=[{"name": "user_input", "type": "string"}],
        context_slots=["user_profile"],
    )
    created = await svc.create(asset)
    assert created.name == "test-prompt"
    assert created.version == 1
    assert created.status == "draft"
    assert created.checksum
    assert created.prompt_asset_id

    fetched = await svc.get(created.prompt_asset_id)
    assert fetched is not None
    assert fetched.name == "test-prompt"
    assert fetched.segments == {"system": "You are helpful."}
    assert fetched.variables == [{"name": "user_input", "type": "string"}]
    assert fetched.context_slots == ["user_profile"]


async def test_save_draft_cas(svc: PromptAssetService) -> None:
    asset = PromptAsset(
        company_id="comp-1",
        name="draft-test",
        segments={"system": "v1"},
    )
    created = await svc.create(asset)

    updated = await svc.save_draft(created, expected_version=1)
    assert updated.version == 2
    assert updated.name == "draft-test"

    with pytest.raises(AcosError) as exc_info:
        await svc.save_draft(created, expected_version=1)
    assert exc_info.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_save_draft_updates_checksum(svc: PromptAssetService) -> None:
    asset = PromptAsset(
        company_id="comp-1",
        name="checksum-test",
        segments={"system": "v1"},
    )
    created = await svc.create(asset)
    old_checksum = created.checksum

    updated = await svc.save_draft(created, expected_version=1)
    updated.name = "checksum-test-v2"
    re_saved = await svc.save_draft(updated, expected_version=2)
    assert re_saved.checksum != old_checksum


async def test_list_by_company(svc: PromptAssetService) -> None:
    for i in range(3):
        await svc.create(
            PromptAsset(company_id="comp-A", name=f"asset-{i}", segments={"s": str(i)})
        )
    await svc.create(
        PromptAsset(company_id="comp-B", name="other", segments={"s": "b"})
    )

    a_assets = await svc.list_by_company("comp-A")
    assert len(a_assets) == 3

    b_assets = await svc.list_by_company("comp-B")
    assert len(b_assets) == 1

    global_asset = await svc.create(
        PromptAsset(company_scope="global", name="global-p", segments={"s": "g"})
    )
    global_assets = await svc.list_by_company(None)
    assert any(a.prompt_asset_id == global_asset.prompt_asset_id for a in global_assets)


async def test_list_by_status_filter(svc: PromptAssetService) -> None:
    await svc.create(
        PromptAsset(company_id="comp-1", name="filter-test", segments={"s": "1"})
    )
    draft_assets = await svc.list_by_company("comp-1", status="draft")
    assert len(draft_assets) == 1

    published_assets = await svc.list_by_company("comp-1", status="published")
    assert len(published_assets) == 0


async def test_create_version(svc: PromptAssetService) -> None:
    asset = await svc.create(
        PromptAsset(company_id="comp-1", name="version-test", segments={"s": "v1"})
    )
    v2 = await svc.create_version(asset.prompt_asset_id, from_version=1)
    assert v2.version == 2
    assert v2.name == "version-test"
    assert v2.status == "draft"
    assert v2.prompt_asset_id == asset.prompt_asset_id

    fetched = await svc.get(v2.prompt_asset_id)
    assert fetched is not None
    assert fetched.version == 2


async def test_create_version_nonexistent(svc: PromptAssetService) -> None:
    with pytest.raises(AcosError) as exc_info:
        await svc.create_version("nonexistent", from_version=1)
    assert exc_info.value.code == "CAP-VERSION-IMMUTABLE"


async def test_get_nonexistent(svc: PromptAssetService) -> None:
    result = await svc.get("nonexistent")
    assert result is None


async def test_checksum_deterministic(svc: PromptAssetService) -> None:
    asset1 = PromptAsset(
        company_id="comp-1", name="cs-test", segments={"a": 1}, variables=[{"x": 1}]
    )
    asset2 = PromptAsset(
        company_id="comp-2", name="cs-test", segments={"a": 1}, variables=[{"x": 1}]
    )
    assert asset1.compute_checksum() == asset2.compute_checksum()
    assert asset1.compute_checksum() == asset1.compute_checksum()
