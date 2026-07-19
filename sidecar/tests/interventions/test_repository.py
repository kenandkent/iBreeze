"""HumanIntervention 仓库测试。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.interventions.repository import InterventionRepository
from acos.store.migrator import Migrator


@pytest.fixture
async def conn(tmp_path: Path) -> aiosqlite.Connection:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(str(Path(__file__).resolve().parents[2] / "migrations"))
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    return db


@pytest.fixture
def repo() -> InterventionRepository:
    return InterventionRepository()


async def test_create_intervention(conn: aiosqlite.Connection, repo: InterventionRepository) -> None:
    item = await repo.create_or_get_open(
        conn,
        company_id="c1",
        subtype="approval",
        target_ref="task-001",
        allowed_actions=["approve", "reject"],
        trace_id="t1",
        task_id="task-001",
    )
    assert item.intervention_id
    assert item.company_id == "c1"
    assert item.subtype == "approval"
    assert item.status == "open"
    assert item.allowed_actions == ["approve", "reject"]
    assert item.version == 1


async def test_create_or_get_open_idempotent(
    conn: aiosqlite.Connection, repo: InterventionRepository
) -> None:
    first = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=["approve"], trace_id="t1",
    )
    second = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=["approve"], trace_id="t1",
    )
    assert first.intervention_id == second.intervention_id


async def test_get_intervention(conn: aiosqlite.Connection, repo: InterventionRepository) -> None:
    created = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=[], trace_id="t1",
    )
    fetched = await repo.get(conn, created.intervention_id, "c1")
    assert fetched is not None
    assert fetched.intervention_id == created.intervention_id

    assert await repo.get(conn, "nonexistent", "c1") is None
    assert await repo.get(conn, created.intervention_id, "other-company") is None


async def test_list_open(conn: aiosqlite.Connection, repo: InterventionRepository) -> None:
    await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="a1",
        allowed_actions=[], trace_id="t1",
    )
    await repo.create_or_get_open(
        conn, company_id="c1", subtype="dead_letter", target_ref="a2",
        allowed_actions=[], trace_id="t1",
    )
    await repo.create_or_get_open(
        conn, company_id="c2", subtype="approval", target_ref="a3",
        allowed_actions=[], trace_id="t1",
    )

    all_open = await repo.list_open(conn, "c1")
    assert len(all_open) == 2

    approvals = await repo.list_open(conn, "c1", subtype="approval")
    assert len(approvals) == 1
    assert approvals[0].target_ref == "a1"


async def test_resolve_cas_success(
    conn: aiosqlite.Connection, repo: InterventionRepository
) -> None:
    item = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=["approve"], trace_id="t1",
    )
    ok = await repo.resolve_cas(
        conn, item.intervention_id, "c1",
        expected_version=1, resolution_ref="resolved-ref", resolved_by="user1",
    )
    assert ok is True

    fetched = await repo.get(conn, item.intervention_id, "c1")
    assert fetched is not None
    assert fetched.status == "resolved"
    assert fetched.resolution_ref == "resolved-ref"
    assert fetched.resolved_by == "user1"
    assert fetched.version == 2


async def test_resolve_cas_version_conflict(
    conn: aiosqlite.Connection, repo: InterventionRepository
) -> None:
    item = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=["approve"], trace_id="t1",
    )
    ok = await repo.resolve_cas(
        conn, item.intervention_id, "c1",
        expected_version=2, resolution_ref="ref", resolved_by="user1",
    )
    assert ok is False

    fetched = await repo.get(conn, item.intervention_id, "c1")
    assert fetched is not None
    assert fetched.status == "open"


async def test_cross_company_isolation(
    conn: aiosqlite.Connection, repo: InterventionRepository
) -> None:
    item = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=[], trace_id="t1",
    )
    assert await repo.get(conn, item.intervention_id, "c2") is None

    open_c2 = await repo.list_open(conn, "c2")
    assert len(open_c2) == 0


async def test_closed_can_create_new(
    conn: aiosqlite.Connection, repo: InterventionRepository
) -> None:
    first = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=[], trace_id="t1",
    )
    await repo.resolve_cas(
        conn, first.intervention_id, "c1",
        expected_version=1, resolution_ref="ref", resolved_by="user1",
    )

    second = await repo.create_or_get_open(
        conn, company_id="c1", subtype="approval", target_ref="task-001",
        allowed_actions=[], trace_id="t1",
    )
    assert second.intervention_id != first.intervention_id
    assert second.status == "open"
