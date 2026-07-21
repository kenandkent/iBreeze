"""provider.* 覆盖率补充测试（精简后：provider.list / model.list / runtime.*）。"""

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


# ── register_to ─────────────────────────────────────────

def test_register_to_registers_methods(methods: ProviderMethods) -> None:
    registered: dict[str, object] = {}

    class _Server:
        def register_method(self, name, fn):
            registered[name] = fn

    methods.register_to(_Server())
    for name in (
        "provider.list", "provider.model.list",
        "provider.runtime.start", "provider.runtime.send", "provider.runtime.cancel",
    ):
        assert name in registered
    for name in (
        "provider.create", "provider.agent.list", "provider.models.fetch",
        "provider.probe", "provider.credential.get", "provider.credential.set",
        "provider.credential.revoke",
    ):
        assert name not in registered


# ── provider.list ───────────────────────────────────────

async def test_provider_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._provider_list({})


# ── provider.model.list ─────────────────────────────────

async def test_model_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._model_list({})


async def test_model_list_all_providers(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    r = await methods._model_list({"company_id": "c1"})
    assert len(r["items"]) >= 1


# ── provider.runtime.* 参数校验 ──────────────────────────

async def test_runtime_start_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._runtime_start({})


async def test_runtime_send_requires_session(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._runtime_send({"message": "x"})


async def test_runtime_cancel_requires_run_id(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._runtime_cancel({})
