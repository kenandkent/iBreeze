"""provider.* 覆盖率补充测试：create api/cli 各校验分支、credential
set/get/revoke、agent.list、model.list、models.fetch 各 vendor 分支、
runtime.* 参数校验。

仅测试，不改业务代码。
"""

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
        "provider.list", "provider.create", "provider.agent.list",
        "provider.models.fetch", "provider.model.list", "provider.probe",
        "provider.credential.get", "provider.credential.set",
        "provider.credential.revoke", "provider.runtime.start",
        "provider.runtime.send", "provider.runtime.cancel",
    ):
        assert name in registered


# ── provider.create 校验分支 ─────────────────────────────

async def test_create_rejects_bad_config_type(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"name": "x", "config": [1, 2]})


async def test_create_api_missing_base_url_ok(methods: ProviderMethods, db_path: str) -> None:
    # api 形式 base_url 可空（凭证走 Keychain），不应报错
    await _make_company(db_path)
    r = await methods._provider_create({"name": "x", "provider_type": "api", "config": {}})
    assert r["provider_type"] == "api"


async def test_create_api_bad_base_url_type(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({
            "name": "x", "provider_type": "api", "config": {"base_url": 123},
        })


async def test_create_api_third_party_vendor(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    r = await methods._provider_create({
        "name": "x", "provider_type": "api",
        "config": {"api_vendor": "third_party", "base_url": "https://my.example/v1"},
    })
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        import json
        cur = await conn.execute(
            "SELECT config FROM providers WHERE provider_id=?", (r["provider_id"],)
        )
        cfg = json.loads((await cur.fetchone())["config"])
        assert cfg["api_vendor"] == "third_party"
    finally:
        await conn.close()


async def test_create_cli_unknown_agent(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({
            "name": "x", "provider_type": "cli",
            "config": {"agent": "unknown-agent", "model": "m"},
        })


async def test_create_cli_missing_model(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({
            "name": "x", "provider_type": "cli", "config": {"agent": "opencode"},
        })


async def test_create_cli_cursor_rejects_custom_model(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({
            "name": "x", "provider_type": "cli",
            "config": {"agent": "cursor-cli", "model": "custom"},
        })


async def test_create_cli_cursor_auto_ok(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    r = await methods._provider_create({
        "company_id": "c1", "name": "cursor", "provider_type": "cli",
        "config": {"agent": "cursor-cli", "model": "auto"},
    })
    assert r["provider_type"] == "cli"


async def test_create_requires_name(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"provider_type": "api"})


async def test_create_rejects_unknown_type(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"name": "x", "provider_type": "grpc"})


# ── provider.agent.list ─────────────────────────────────

async def test_agent_list_all_vendors(methods: ProviderMethods) -> None:
    r = await methods._agent_list({})
    ids = {a["agent_id"] for a in r["agents"]}
    assert ids == {"cursor-cli", "claude-code", "codex-cli", "opencode"}
    codex = next(a for a in r["agents"] if a["agent_id"] == "codex-cli")
    assert any(m["model"] == "gpt-5.1-codex" for m in codex["models"])


# ── provider.model.list ─────────────────────────────────

async def test_model_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._model_list({})


async def test_model_list_from_provider_models(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    cli = await methods._provider_create({
        "company_id": "c1", "name": "opencode", "provider_type": "cli",
        "config": {"agent": "opencode", "model": "anthropic/claude-sonnet-5"},
    })
    r = await methods._model_list({"company_id": "c1", "provider_id": cli["provider_id"]})
    assert any(m["model"] == "anthropic/claude-sonnet-5" for m in r["items"])


async def test_model_list_all_providers(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    r = await methods._model_list({"company_id": "c1"})
    assert len(r["items"]) >= 1


# ── provider.models.fetch 各 vendor 分支 ─────────────────

async def test_models_fetch_no_key_anthropic_fallback(methods: ProviderMethods) -> None:
    r = await methods._models_fetch({"api_vendor": "anthropic"})
    assert r["source"] == "fallback"
    assert any(m["model"] == "claude-sonnet-5" for m in r["models"])


async def test_models_fetch_no_key_openai_fallback(methods: ProviderMethods) -> None:
    r = await methods._models_fetch({"api_vendor": "openai"})
    assert r["source"] == "fallback"
    assert any(m["model"] == "gpt-5.1-codex" for m in r["models"])


async def test_models_fetch_unknown_vendor_empty_fallback(methods: ProviderMethods) -> None:
    r = await methods._models_fetch({"api_vendor": "weird"})
    assert r["source"] == "fallback"
    assert r["models"] == []


async def test_models_fetch_third_party_without_base_url_errors(methods: ProviderMethods) -> None:
    # third_party 有 key 但无 base_url → 走 _fetch_vendor_models 抛错 → 降级 fallback
    r = await methods._models_fetch({"api_vendor": "third_party", "api_key": "sk-x"})
    assert r["source"] == "fallback"
    assert r["error_message"]


async def test_models_fetch_live_returns_empty_uses_fallback(
    methods: ProviderMethods, monkeypatch
) -> None:
    import httpx

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": []}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    r = await methods._models_fetch({"api_vendor": "openai", "api_key": "sk-x"})
    assert r["source"] == "fallback"
    assert r["error_message"] == "厂商返回为空，使用内置清单"


# ── provider.credential.* ───────────────────────────────

async def test_credential_set_get_roundtrip(methods: ProviderMethods) -> None:
    await methods._credential_set({
        "company_id": "c1", "provider_id": "openai",
        "credential_slot": "default", "credential": "sk-abc",
    })
    r = await methods._credential_get({"company_id": "c1", "provider_id": "openai"})
    assert r["credential"] == "sk-abc"


async def test_credential_revoke(methods: ProviderMethods) -> None:
    await methods._credential_set({
        "company_id": "c1", "provider_id": "openai",
        "credential_slot": "default", "credential": "sk-abc",
    })
    await methods._credential_revoke({"company_id": "c1", "provider_id": "openai"})
    with pytest.raises(AcosError):
        await methods._credential_get({"company_id": "c1", "provider_id": "openai"})


async def test_credential_get_unknown_fails(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._credential_get({"company_id": "cX", "provider_id": "openai"})


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


# ── provider.list ───────────────────────────────────────

async def test_provider_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._provider_list({})
