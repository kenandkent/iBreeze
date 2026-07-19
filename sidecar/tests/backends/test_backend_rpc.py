"""Backend Registry/Health RPC 测试（backend.*）。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from acos.backends.service import BackendLeaseManager, BackendService
from acos.rpc.errors import AcosError
from acos.rpc.methods_backend import BackendMethods
from acos.store.migrator import Migrator


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(p)


@pytest.fixture
def methods(db_path: str) -> BackendMethods:
    return BackendMethods(db_path)


async def _make_company(db_path: str, company_id: str, status: str = "active") -> None:
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO companies (company_id, name, status, root_department_id, version)
               VALUES (?, ?, ?, ?, 1)""",
            (company_id, f"co-{company_id}", status, f"dept-{company_id}"),
        )
        await db.commit()


async def _seed_backend(
    db_path: str,
    *,
    company_id: str,
    backend_id: str,
    status: str = "enabled",
    health: str = "healthy",
    concurrency_limit: int = 2,
    workspace_root: str = "/tmp/ws-default",
    capabilities: list[str] | None = None,
    workspace_types: list[str] | None = None,
) -> None:
    import aiosqlite
    import json

    capabilities = capabilities or ["agent_runtime", "filesystem_io", "readonly_io"]
    workspace_types = workspace_types or ["TaskWorkspace", "ReadOnlyWorkspace"]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO backends
               (backend_id, company_id, name, backend_type, status, health_status,
                capabilities, workspace_types, workspace_root, concurrency_limit, version)
               VALUES (?, ?, ?, 'local_process', ?, ?, ?, ?, ?, ?, 1)""",
            (
                backend_id, company_id, f"be-{backend_id}",
                status, health,
                json.dumps(capabilities), json.dumps(workspace_types),
                workspace_root, concurrency_limit,
            ),
        )
        await db.commit()


async def _set_default(db_path: str, company_id: str, backend_id: str) -> None:
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO company_backend_defaults
               (default_id, company_id, backend_id, is_archived, version)
               VALUES (?, ?, ?, 0, 1)""",
            (str(uuid.uuid4()), company_id, backend_id),
        )
        await db.commit()


async def _count_defaults(db_path: str, company_id: str) -> int:
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM company_backend_defaults WHERE company_id = ? AND is_archived = 0",
            (company_id,),
        )
        return (await cur.fetchone())[0]


async def _count_audit(db_path: str, action: str) -> int:
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM backend_change_audit WHERE action = ?", (action,)
        )
        return (await cur.fetchone())[0]


# ── 默认唯一 ──────────────────────────────────────────────


async def test_create_seeds_exactly_one_default(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await methods._create({
        "company_id": "c1",
        "name": "b1",
        "workspace_root": "/tmp/ws-b1",
    })
    assert await _count_defaults(db_path, "c1") == 1


async def test_set_default_uniqueness_cas(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1")
    await _seed_backend(db_path, company_id="c1", backend_id="b2", workspace_root="/tmp/ws-b2")
    await _set_default(db_path, "c1", "b1")

    await methods._set_default({"backend_id": "b2", "expected_version": 1})
    assert await _count_defaults(db_path, "c1") == 1

    # b1 已不再是默认
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT is_archived FROM company_backend_defaults WHERE company_id='c1' AND backend_id='b1'"
        )
        assert (await cur.fetchone())[0] == 1


import aiosqlite


async def test_set_default_cas_conflict(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1")
    await _seed_backend(db_path, company_id="c1", backend_id="b2", workspace_root="/tmp/ws-b2")
    await _set_default(db_path, "c1", "b1")

    # 用错误的 expected_version 触发 CAS 冲突
    with pytest.raises(AcosError):
        await methods._set_default({"backend_id": "b2", "expected_version": 999})


# ── 跨公司拒绝 ────────────────────────────────────────────


async def test_list_isolated_by_company(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _make_company(db_path, "c2")
    await _seed_backend(db_path, company_id="c1", backend_id="b1")
    await _seed_backend(db_path, company_id="c2", backend_id="b2", workspace_root="/tmp/ws-b2")

    l1 = await methods._list({"company_id": "c1"})
    l2 = await methods._list({"company_id": "c2"})
    assert [b["backend_id"] for b in l1] == ["b1"]
    assert [b["backend_id"] for b in l2] == ["b2"]


async def test_check_availability_cross_company_denied(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _make_company(db_path, "c2")
    await _seed_backend(db_path, company_id="c1", backend_id="b1")
    with pytest.raises(AcosError):
        await methods._check_availability({"backend_id": "b1", "company_id": "c2"})


# ── 非法状态跃迁 ──────────────────────────────────────────


async def test_enable_from_draining_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="draining")
    with pytest.raises(AcosError):
        await methods._enable({"backend_id": "b1", "expected_version": 1})


async def test_drain_from_disabled_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="disabled")
    with pytest.raises(AcosError):
        await methods._drain({"backend_id": "b1", "expected_version": 1})


async def test_archive_from_enabled_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="enabled")
    with pytest.raises(AcosError):
        await methods._archive({"backend_id": "b1", "expected_version": 1})


async def test_enable_requires_healthy(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="disabled", health="unknown")
    with pytest.raises(AcosError):
        await methods._enable({"backend_id": "b1", "expected_version": 1})


# ── 默认 / 有 lease 归档拒绝 ─────────────────────────────


async def test_archive_default_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="disabled")
    await _set_default(db_path, "c1", "b1")
    with pytest.raises(AcosError):
        await methods._archive({"backend_id": "b1", "expected_version": 1})


async def test_drain_default_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="enabled")
    await _set_default(db_path, "c1", "b1")
    with pytest.raises(AcosError):
        await methods._drain({"backend_id": "b1", "expected_version": 1})


async def test_archive_with_held_lease_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="disabled")
    lm = BackendLeaseManager(db_path)
    await lm.bind("b1", "c1", run_id="run-1")
    with pytest.raises(AcosError):
        await methods._archive({"backend_id": "b1", "expected_version": 1})


# ── update 降并发不杀 lease ───────────────────────────────


async def test_update_lower_concurrency_than_held_rejected(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", concurrency_limit=2)
    lm = BackendLeaseManager(db_path)
    await lm.bind("b1", "c1", run_id="run-1")
    await lm.bind("b1", "c1", run_id="run-2")
    # 当前 held=2，尝试降到 1（低于 held）应拒绝
    with pytest.raises(AcosError):
        await methods._update({
            "backend_id": "b1",
            "expected_version": 1,
            "concurrency_limit": 1,
        })

    # lease 仍然存活
    assert len(await lm.list_active("b1")) == 2


async def test_update_raise_concurrency_keeps_lease(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", concurrency_limit=1)
    lm = BackendLeaseManager(db_path)
    await lm.bind("b1", "c1", run_id="run-1")
    await methods._update({
        "backend_id": "b1",
        "expected_version": 1,
        "concurrency_limit": 3,
    })
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT concurrency_limit FROM backends WHERE backend_id='b1'")
        assert (await cur.fetchone())[0] == 3
    assert len(await lm.list_active("b1")) == 1


# ── probe 改变健康状态 ────────────────────────────────────


async def test_probe_sets_health_unknown_to_healthy(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(
        db_path, company_id="c1", backend_id="b1", status="disabled",
        health="unknown", workspace_root="/tmp/probe-ws",
    )
    res = await methods._probe({"backend_id": "b1"})
    assert res["health_status"] in ("healthy", "degraded")
    assert res["before_health_status"] == "unknown"


async def test_probe_git_cli_checks_availability(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(
        db_path, company_id="c1", backend_id="b1", status="disabled",
        health="unknown", workspace_root="/tmp/probe-ws-git",
        capabilities=["agent_runtime", "filesystem_io", "readonly_io", "git_cli"],
        workspace_types=["TaskWorkspace", "ReadOnlyWorkspace", "GitWorktreeWorkspace"],
    )
    res = await methods._probe({"backend_id": "b1"})
    assert res["git_cli_ok"] in (True, False)  # 真实检查，不为 None


# ── checkAvailability 返回真实容量 ───────────────────────


async def test_check_availability_real_capacity(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", concurrency_limit=2)
    lm = BackendLeaseManager(db_path)
    await lm.bind("b1", "c1", run_id="run-1")

    av = await methods._check_availability({"backend_id": "b1", "company_id": "c1"})
    assert av["concurrency_limit"] == 2
    assert av["active_leases"] == 1
    assert av["available"] == 1


async def test_check_availability_with_request_ref(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", concurrency_limit=1)
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO backend_queue_entries
               (entry_id, backend_id, company_id, run_id, wait_reason, status, created_at)
               VALUES ('q1', 'b1', 'c1', 'run-1', 'backend_capacity', 'waiting', datetime('now'))"""
        )
        await db.commit()
    av = await methods._check_availability({
        "backend_id": "b1", "company_id": "c1", "request_ref": "q1",
    })
    assert av["backend_position"] == 1
    assert av["wait_reason"] == "backend_capacity"


# ── 写方法带审计 ──────────────────────────────────────────


async def test_write_methods_emit_audit(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    await _seed_backend(db_path, company_id="c1", backend_id="b1", status="disabled", health="healthy")
    await methods._enable({"backend_id": "b1", "expected_version": 1})
    assert await _count_audit(db_path, "enable") == 1

    await methods._drain({"backend_id": "b1", "expected_version": 2})
    assert await _count_audit(db_path, "drain") == 1


# ── 公司隔离写保护 ────────────────────────────────────────


async def test_create_rejected_for_missing_company(db_path: str, methods: BackendMethods) -> None:
    with pytest.raises(AcosError):
        await methods._create({"company_id": "ghost", "name": "x"})


# ── 非法能力/类型校验 ─────────────────────────────────────


async def test_create_rejects_unknown_backend_type(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    with pytest.raises(AcosError):
        await methods._create({
            "company_id": "c1", "name": "x", "backend_type": "cloud_gpu",
        })


async def test_create_rejects_git_cli_without_git_workspace(db_path: str, methods: BackendMethods) -> None:
    await _make_company(db_path, "c1")
    with pytest.raises(AcosError):
        await methods._create({
            "company_id": "c1",
            "name": "x",
            "workspace_root": "/tmp/ws-x",
            "capabilities": ["agent_runtime", "filesystem_io", "readonly_io", "git_cli"],
        })
