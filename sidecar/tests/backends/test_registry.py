"""Backend Service / Scheduler / LeaseManager 测试。"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from acos.backends.models import Backend, BackendLease, BackendQueueEntry
from acos.backends.service import BackendLeaseManager, BackendScheduler, BackendService
from acos.rpc.errors import AcosError
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
def svc(db_path: str) -> BackendService:
    return BackendService(db_path)


@pytest.fixture
def scheduler(db_path: str) -> BackendScheduler:
    return BackendScheduler(db_path)


@pytest.fixture
def lease_mgr(db_path: str) -> BackendLeaseManager:
    return BackendLeaseManager(db_path)


async def _make_backend(svc: BackendService, company_id: str = "comp-1", **extra: object) -> Backend:
    uid = uuid.uuid4().hex[:8]
    data: dict = {
        "backend_id": f"be-{uid}",
        "company_id": company_id,
        "name": f"test-backend-{uid}",
        "backend_type": "local_process",
        "status": "enabled",
        "health_status": "healthy",
        "capabilities": ["gpu"],
        "workspace_types": ["code"],
        "workspace_root": "/tmp/ws",
        "concurrency_limit": 2,
    }
    data.update(extra)  # type: ignore[arg-type]
    return await svc.create(Backend(**data))


# ── BackendService ──


async def test_create_and_get_backend(svc: BackendService) -> None:
    backend = await _make_backend(svc)
    assert backend.backend_id
    assert backend.status == "enabled"

    fetched = await svc.get(backend.backend_id)
    assert fetched is not None
    assert fetched.name == backend.name
    assert fetched.capabilities == ["gpu"]


async def test_list_by_company(svc: BackendService) -> None:
    await _make_backend(svc, company_id="comp-A")
    await _make_backend(svc, company_id="comp-A")
    await _make_backend(svc, company_id="comp-B")

    a_list = await svc.list_by_company("comp-A")
    assert len(a_list) == 2
    b_list = await svc.list_by_company("comp-B")
    assert len(b_list) == 1


async def test_update_status(svc: BackendService) -> None:
    backend = await _make_backend(svc)
    updated = await svc.update_status(backend.backend_id, "disabled", "degraded")
    assert updated is not None
    assert updated.status == "disabled"
    assert updated.health_status == "degraded"
    assert updated.version == 2


async def test_update_status_nonexistent(svc: BackendService) -> None:
    result = await svc.update_status("nonexistent", "enabled")
    assert result is None


# ── BackendScheduler ──


async def test_select_backend_found(svc: BackendService, scheduler: BackendScheduler) -> None:
    backend = await _make_backend(svc)
    selected = await scheduler.select_backend("comp-1")
    assert selected is not None
    assert selected.backend_id == backend.backend_id


async def test_select_backend_filters_by_capability(
    svc: BackendService, scheduler: BackendScheduler
) -> None:
    await _make_backend(svc, capabilities=["gpu"])
    selected = await scheduler.select_backend("comp-1", required_capabilities=["tpu"])
    assert selected is None


async def test_select_backend_respects_capacity(
    svc: BackendService, scheduler: BackendScheduler, lease_mgr: BackendLeaseManager
) -> None:
    backend = await _make_backend(svc, concurrency_limit=1)
    await lease_mgr.bind(backend.backend_id, "comp-1", run_id="run-1")
    selected = await scheduler.select_backend("comp-1")
    assert selected is None


async def test_enqueue_and_acquire(svc: BackendService, scheduler: BackendScheduler) -> None:
    backend = await _make_backend(svc)
    entry = await scheduler.enqueue(backend.backend_id, "comp-1", run_id="run-1")
    assert entry.status == "waiting"

    acquired = await scheduler.acquire_next(backend.backend_id)
    assert acquired is not None
    assert acquired.entry_id == entry.entry_id

    next_one = await scheduler.acquire_next(backend.backend_id)
    assert next_one is None


# ── BackendLeaseManager ──


async def test_bind_and_list_active(lease_mgr: BackendLeaseManager) -> None:
    lease = await lease_mgr.bind("be-1", "comp-1", run_id="run-1")
    assert lease.lease_id
    assert lease.status == "active"

    active = await lease_mgr.list_active("be-1")
    assert len(active) == 1


async def test_heartbeat(lease_mgr: BackendLeaseManager) -> None:
    lease = await lease_mgr.bind("be-1", "comp-1", run_id="run-1")
    ok = await lease_mgr.heartbeat(lease.lease_id)
    assert ok is True


async def test_heartbeat_nonexistent(lease_mgr: BackendLeaseManager) -> None:
    ok = await lease_mgr.heartbeat("nonexistent")
    assert ok is False


async def test_release(lease_mgr: BackendLeaseManager) -> None:
    lease = await lease_mgr.bind("be-1", "comp-1", run_id="run-1")
    ok = await lease_mgr.release(lease.lease_id)
    assert ok is True

    active = await lease_mgr.list_active("be-1")
    assert len(active) == 0


async def test_release_nonexistent(lease_mgr: BackendLeaseManager) -> None:
    ok = await lease_mgr.release("nonexistent")
    assert ok is False
