"""provider.* RPC 契约测试（精简后：provider.list / model.list / runtime.*）。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.organization.principal import reset_local_owner_cache
from acos.rpc.errors import AcosError
from acos.rpc.methods_provider import ProviderMethods
from acos.store.migrator import Migrator


@pytest.fixture(autouse=True)
def _reset_owner() -> None:
    reset_local_owner_cache()


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(p)


@pytest.fixture
def methods(db_path: str) -> ProviderMethods:
    return ProviderMethods(db_path)


async def _make_company(db_path: str, company_id: str = "c1", version: int = 1) -> None:
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute(
            """INSERT INTO companies
               (company_id, name, status, default_provider_policy, default_budget_policy, version)
               VALUES (?, ?, 'active', '{}', '{}', ?)""",
            (company_id, f"Company {company_id}", version),
        )
        await conn.commit()
    finally:
        await conn.close()


# ── provider.list ──


async def test_provider_list_imports_manifest(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    result = await methods._provider_list({"company_id": "c1"})
    ids = {p["provider_id"] for p in result["items"]}
    assert "openai" in ids
    assert set(result["tier_mapping"].keys()) == {"free", "standard", "premium"}


async def test_provider_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._provider_list({})


# ── model.list ──


async def test_model_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._model_list({})


# ── runtime.* ──


async def test_runtime_start_send_cancel(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    started = await methods._runtime_start({"company_id": "c1", "model": "fake-model-1"})
    session_id = started["session_id"]
    assert session_id.startswith("rs-")

    sent = await methods._runtime_send({"session_id": session_id, "message": "hello"})
    assert sent["status"] == "completed"
    assert any(e["event_type"] == "message" for e in sent["events"])
    assert all(e["run_id"] == sent["run_id"] for e in sent["events"])

    cancelled = await methods._runtime_cancel({"run_id": sent["run_id"]})
    assert cancelled["ok"] is True


async def test_runtime_send_unknown_session(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._runtime_send({"session_id": "rs-nope", "message": "x"})
