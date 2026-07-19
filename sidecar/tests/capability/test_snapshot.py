"""Capability 快照测试。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.capability.models import compute_checksum
from acos.capability.snapshot import CapabilitySnapshot
from acos.store.migrator import Migrator


@pytest.fixture
async def db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(db_path)


async def _insert_capability(conn: aiosqlite.Connection, cap_id: str) -> None:
    await conn.execute(
        """INSERT INTO capabilities
           (capability_id, company_scope, company_id, name,
            checksum, version, status, created_at, updated_at)
           VALUES (?, 'company', 'comp-1', 'Cap', 'chk', 1,
            'draft', datetime('now'), datetime('now'))""",
        (cap_id,),
    )


async def _insert_skill(
    conn: aiosqlite.Connection, skill_id: str, checksum: str
) -> None:
    await conn.execute(
        """INSERT INTO skills
           (skill_id, company_scope, company_id, name,
            prompt_asset_id, prompt_asset_version, prompt_asset_checksum,
            checksum, version, status, created_at, updated_at)
           VALUES (?, 'company', 'comp-1', ?, 'pa-1', 1, 'pa-csum',
            ?, 1, 'draft', datetime('now'), datetime('now'))""",
        (skill_id, skill_id, checksum),
    )


async def _insert_binding(
    conn: aiosqlite.Connection,
    bind_id: str,
    cap_id: str,
    skill_id: str,
    checksum: str,
    ordinal: int = 0,
) -> None:
    await conn.execute(
        """INSERT INTO skill_bindings
           (binding_id, capability_id, capability_version,
            skill_id, skill_version, skill_version_checksum, ordinal)
           VALUES (?, ?, 1, ?, 1, ?, ?)""",
        (bind_id, cap_id, skill_id, checksum, ordinal),
    )


async def test_build_snapshot_success(db: str) -> None:
    async with aiosqlite.connect(db) as conn:
        await _insert_capability(conn, "cap-1")
        skill_checksum = compute_checksum({"name": "skill1"})
        await _insert_skill(conn, "skill-1", skill_checksum)
        await _insert_binding(conn, "bind-1", "cap-1", "skill-1", skill_checksum)
        await conn.commit()

    snapshot_svc = CapabilitySnapshot()
    async with aiosqlite.connect(db) as conn:
        lock = await snapshot_svc.build_snapshot(conn, "cap-1", 1)

    assert lock.snapshot_id
    assert lock.capability_id == "cap-1"
    assert lock.capability_version == 1
    assert len(lock.dependency_tree) == 1
    assert lock.dependency_tree[0]["skill_id"] == "skill-1"


async def test_build_snapshot_checksum_mismatch(db: str) -> None:
    async with aiosqlite.connect(db) as conn:
        await _insert_capability(conn, "cap-2")
        await _insert_skill(conn, "skill-2", "real-checksum")
        await _insert_binding(
            conn, "bind-2", "cap-2", "skill-2", "wrong-checksum"
        )
        await conn.commit()

    snapshot_svc = CapabilitySnapshot()
    async with aiosqlite.connect(db) as conn:
        with pytest.raises(ValueError, match="Checksum mismatch"):
            await snapshot_svc.build_snapshot(conn, "cap-2", 1)


async def test_verify_snapshot(db: str) -> None:
    async with aiosqlite.connect(db) as conn:
        await _insert_capability(conn, "cap-3")
        skill_checksum = compute_checksum({"name": "skill3"})
        await _insert_skill(conn, "skill-3", skill_checksum)
        await _insert_binding(conn, "bind-3", "cap-3", "skill-3", skill_checksum)
        await conn.commit()

    snapshot_svc = CapabilitySnapshot()
    async with aiosqlite.connect(db) as conn:
        lock = await snapshot_svc.build_snapshot(conn, "cap-3", 1)
        assert await snapshot_svc.verify_snapshot(conn, lock.snapshot_id) is True
