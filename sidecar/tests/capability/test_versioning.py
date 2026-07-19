"""发布状态机测试（真实 *_versions 表）。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.capability.versioning import VersioningService
from acos.rpc.errors import AcosError
from acos.store.migrator import Migrator


@pytest.fixture
async def svc(tmp_path: Path) -> VersioningService:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            """INSERT INTO skill_versions
               (skill_version_id, skill_id, version, name, prompt_asset_id,
                prompt_asset_version, prompt_asset_checksum, tool_bindings,
                knowledge_refs, input_schema, output_schema, checksum, status, created_at, updated_at)
               VALUES ('sv-1', 'skill-1', 1, 's', 'pa', 1, 'x', '[]', '[]', '{}', '{}', 'c', 'draft', datetime('now'), datetime('now'))"""
        )
        await db.execute(
            """INSERT INTO skills
               (skill_id, company_scope, company_id, name, prompt_asset_id,
                prompt_asset_version, prompt_asset_checksum, tool_bindings,
                knowledge_refs, input_schema, output_schema, checksum,
                version, status, created_at, updated_at)
               VALUES ('skill-1', 'company', 'comp-1', 's', 'pa', 1, 'x', '[]', '[]', '{}', '{}', 'c', 1, 'draft', datetime('now'), datetime('now'))"""
        )
        await db.commit()
    return VersioningService(str(db_path))


async def _status(svc: VersioningService, table: str, entity_id: str) -> str:
    id_col = {
        "skill_versions": "skill_id",
        "prompt_asset_versions": "prompt_asset_id",
        "capability_versions": "capability_id",
    }[table]
    async with aiosqlite.connect(svc._db_path) as db:
        cursor = await db.execute(
            f"SELECT status FROM {table} WHERE {id_col} = ? AND version = 1",
            (entity_id,),
        )
        row = await cursor.fetchone()
        return row[0]


async def test_submit_review(svc: VersioningService) -> None:
    await svc.submit_review("skill", "skill-1", 1)
    assert await _status(svc, "skill_versions", "skill-1") == "review"


async def test_publish_after_quality_gate(svc: VersioningService) -> None:
    await svc.submit_review("skill", "skill-1", 1)
    with pytest.raises(AcosError) as exc_info:
        await svc.publish("skill", "skill-1", 1)
    assert exc_info.value.code == "CAP-QUALITY-GATE-FAILED"


async def test_deprecate(svc: VersioningService) -> None:
    async with aiosqlite.connect(svc._db_path) as db:
        await db.execute(
            "UPDATE skill_versions SET status = 'published' WHERE skill_id = 'skill-1' AND version = 1"
        )
        await db.execute(
            "UPDATE skills SET status = 'published' WHERE skill_id = 'skill-1'"
        )
        await db.commit()
    await svc.deprecate("skill", "skill-1", 1)
    assert await _status(svc, "skill_versions", "skill-1") == "deprecated"
    async with aiosqlite.connect(svc._db_path) as db:
        cursor = await db.execute("SELECT status FROM skills WHERE skill_id = 'skill-1'")
        assert (await cursor.fetchone())[0] == "deprecated"


async def test_archive(svc: VersioningService) -> None:
    async with aiosqlite.connect(svc._db_path) as db:
        await db.execute(
            "UPDATE skill_versions SET status = 'deprecated' WHERE skill_id = 'skill-1' AND version = 1"
        )
        await db.execute(
            "UPDATE skills SET status = 'deprecated' WHERE skill_id = 'skill-1'"
        )
        await db.commit()
    await svc.archive("skill", "skill-1", 1)
    assert await _status(svc, "skill_versions", "skill-1") == "archived"


async def test_invalid_transition(svc: VersioningService) -> None:
    with pytest.raises(AcosError) as exc_info:
        await svc.publish("skill", "skill-1", 1)
    assert exc_info.value.code == "CAP-STATE-INVALID"
