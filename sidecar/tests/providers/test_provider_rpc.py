"""provider.* RPC 契约测试（P6-T1a/P6-T2/P6-T3）。"""

from __future__ import annotations

import uuid
import json
from pathlib import Path

import aiosqlite
import pytest

from acos.organization.principal import reset_local_owner_cache
from acos.providers import pricing as pm
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


# ── provider.list / model.list ──


async def test_provider_list_imports_manifest(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    result = await methods._provider_list({"company_id": "c1"})
    ids = {p["provider_id"] for p in result["items"]}
    assert "openai" in ids
    assert set(result["tier_mapping"].keys()) == {"free", "standard", "premium"}


async def test_provider_create_api_and_list_status(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    created = await methods._provider_create({
        "name": "MyOpenAI",
        "provider_type": "api",
        "config": {"base_url": "https://api.openai.com/v1"},
    })
    assert created["provider_id"].startswith("pv-")
    assert created["name"] == "MyOpenAI"
    assert created["provider_type"] == "api"
    assert created["status"] == "active"

    result = await methods._provider_list({"company_id": "c1"})
    oc = next(p for p in result["items"] if p["provider_id"] == created["provider_id"])
    assert oc["status"] == "active"
    assert oc["provider_type"] == "api"


async def test_provider_create_cli_stores_agent_and_model(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    created = await methods._provider_create({
        "name": "opencode",
        "provider_type": "cli",
        "config": {"agent": "opencode", "model": "anthropic/claude-sonnet-4"},
    })
    assert created["provider_type"] == "cli"

    conn = await aiosqlite.connect(db_path)
    try:
        cur = await conn.execute("SELECT config FROM providers WHERE provider_id = ?", (created["provider_id"],))
        row = await cur.fetchone()
        cfg = json.loads(row[0])
    finally:
        await conn.close()
    assert cfg == {"agent": "opencode", "model": "anthropic/claude-sonnet-4"}


async def test_provider_create_requires_name(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"provider_type": "api"})


async def test_provider_create_rejects_bad_config(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"name": "x", "config": "not-an-object"})


async def test_provider_create_rejects_unknown_type(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"name": "x", "provider_type": "agent"})


async def test_provider_create_cli_rejects_unknown_agent(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"name": "x", "provider_type": "cli", "config": {"agent": "nope", "model": "m"}})


async def test_provider_create_cli_requires_model(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._provider_create({"name": "x", "provider_type": "cli", "config": {"agent": "opencode"}})


async def test_provider_agent_list_returns_fixed_agents(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    result = await methods._agent_list({})
    agent_ids = {a["agent_id"] for a in result["agents"]}
    assert agent_ids == {"cursor-cli", "claude-code", "codex-cli", "opencode"}
    cursor = next(a for a in result["agents"] if a["agent_id"] == "cursor-cli")
    assert [m["model"] for m in cursor["models"]] == ["auto"]
    opencode = next(a for a in result["agents"] if a["agent_id"] == "opencode")
    assert any(m["model"] == "anthropic/claude-sonnet-4" for m in opencode["models"])


async def test_model_list_requires_company(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._model_list({})


async def test_model_list_merges_builtin_and_private(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    # 登记 c1 私有模型 + 价格
    await methods._pricing_policy_update({
        "company_id": "c1", "provider_id": "openai", "model": "custom-x",
        "currency": "USD", "effective_at": "2026-01-01T00:00:00Z", "source": "manual",
        "pricing": {"input_per_1m_micros": 1000, "output_per_1m_micros": 2000},
        "model_spec": {"tier": "standard", "context_window": 8000, "supports": ["chat"],
                       "billing_mode": "metered", "enforces_output_cap": True},
    })
    result = await methods._model_list({"company_id": "c1"})
    models = {m["model"] for m in result["items"]}
    assert "gpt-4o-2024-08-06" in models
    assert "custom-x" in models
    # c2 看不到 c1 私有模型
    await _make_company(db_path, "c2")
    r2 = await methods._model_list({"company_id": "c2"})
    assert "custom-x" not in {m["model"] for m in r2["items"]}


# ── pricingPolicy.update ──


async def test_pricing_update_injects_verified_at(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    res = await methods._pricing_policy_update({
        "company_id": "c1", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
        "currency": "USD", "effective_at": "2026-01-01T00:00:00Z", "source": "manual",
        "pricing": {"input_per_1m_micros": 1000, "output_per_1m_micros": 2000},
    })
    assert res["pricing_version_id"].startswith("pv-")
    assert res["verified_at"]


async def test_pricing_update_rejects_client_verified_at(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._pricing_policy_update({
            "company_id": "c1", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
            "currency": "USD", "effective_at": "2026-01-01T00:00:00Z", "source": "manual",
            "verified_at": "2020-01-01T00:00:00Z",
            "pricing": {"input_per_1m_micros": 1000, "output_per_1m_micros": 2000},
        })


async def test_pricing_update_history_no_overwrite(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    params = {
        "company_id": "c1", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
        "currency": "USD", "effective_at": "2026-01-01T00:00:00Z", "source": "manual",
        "pricing": {"input_per_1m_micros": 1000, "output_per_1m_micros": 2000},
    }
    await methods._pricing_policy_update(params)
    # 同 effective_at 再写 → 拒绝
    with pytest.raises(AcosError):
        await methods._pricing_policy_update(params)


async def test_pricing_update_rejects_negative(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._pricing_policy_update({
            "company_id": "c1", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
            "currency": "USD", "effective_at": "2026-01-01T00:00:00Z", "source": "manual",
            "pricing": {"input_per_1m_micros": -1, "output_per_1m_micros": 2000},
        })


# ── probe 不改静态能力 ──


async def test_probe_does_not_change_capabilities(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT model, tier, context_window FROM provider_models WHERE provider_id='fake' OR provider_id='openai'")
    before = [dict(r) for r in await cur.fetchall()]
    await conn.close()

    res = await methods._probe({"company_id": "c1", "provider_id": "fake"})
    assert res["available"] is True

    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT model, tier, context_window FROM provider_models WHERE provider_id='fake' OR provider_id='openai'")
    after = [dict(r) for r in await cur.fetchall()]
    await conn.close()
    assert before == after
    # availability 投影已写入
    avail = await methods._registry.get_availability("c1", "fake")
    assert avail is not None and bool(avail["available"]) is True


# ── tierMapping.update ──


async def test_tier_mapping_roundtrip_three_keys(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    res = await methods._tier_mapping_update({
        "company_id": "c1", "expected_company_version": 1,
        "tier": "premium", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
    })
    assert res["company_version"] == 2
    assert set(res["tier_mapping"].keys()) == {"free", "standard", "premium"}
    assert res["tier_mapping"]["premium"] == {"provider_id": "openai", "model": "gpt-4o-2024-08-06"}
    assert res["tier_mapping"]["free"] is None


async def test_tier_mapping_cas_conflict(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    with pytest.raises(AcosError) as ei:
        await methods._tier_mapping_update({
            "company_id": "c1", "expected_company_version": 99,
            "tier": "free", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
        })
    assert ei.value.code == "SYS-OPTIMISTIC-LOCK-CONFLICT"


async def test_tier_mapping_rejects_unknown_model(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    with pytest.raises(AcosError):
        await methods._tier_mapping_update({
            "company_id": "c1", "expected_company_version": 1,
            "tier": "free", "provider_id": "openai", "model": "nonexistent",
        })


async def test_tier_mapping_rejects_bad_tier(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    with pytest.raises(AcosError):
        await methods._tier_mapping_update({
            "company_id": "c1", "expected_company_version": 1, "tier": "vip",
        })


# ── budgetFreeze.clear ──


async def _make_freeze(db_path: str, company_id: str, provider_id: str, run_id: str) -> str:
    fid = f"fz-{uuid.uuid4().hex}"
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute(
            """INSERT INTO provider_budget_freezes
               (freeze_id, company_id, provider_id, trigger_run_id, reason_code, evidence_hash,
                status, version)
               VALUES (?, ?, ?, ?, 'BOUNDED_COST_VIOLATION', 'hash1', 'active', 1)""",
            (fid, company_id, provider_id, run_id),
        )
        await conn.commit()
    finally:
        await conn.close()
    return fid


async def test_freeze_clear_requires_reason(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    fid = await _make_freeze(db_path, "c1", "openai", "run-1")
    with pytest.raises(AcosError):
        await methods._budget_freeze_clear({"company_id": "c1", "freeze_id": fid, "clear_reason": ""})
    with pytest.raises(AcosError):
        await methods._budget_freeze_clear({"company_id": "c1", "freeze_id": fid, "clear_reason": "x" * 1001})


async def test_freeze_clear_still_unsafe_without_price(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    fid = await _make_freeze(db_path, "c1", "openai", "run-1")
    with pytest.raises(AcosError) as ei:
        await methods._budget_freeze_clear({"company_id": "c1", "freeze_id": fid, "clear_reason": "checked"})
    assert ei.value.code == "PROV-FREEZE-STILL-UNSAFE"


async def test_freeze_clear_success_after_price(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    await methods._ensure_manifest()
    await methods._pricing_policy_update({
        "company_id": "c1", "provider_id": "openai", "model": "gpt-4o-2024-08-06",
        "currency": "USD", "effective_at": "2020-01-01T00:00:00Z", "source": "manual",
        "pricing": {"input_per_1m_micros": 1000, "output_per_1m_micros": 2000},
    })
    fid = await _make_freeze(db_path, "c1", "openai", "run-1")
    res = await methods._budget_freeze_clear({"company_id": "c1", "freeze_id": fid, "clear_reason": "reverified"})
    assert res["ok"] is True
    # cleared 不可再清除
    with pytest.raises(AcosError):
        await methods._budget_freeze_clear({"company_id": "c1", "freeze_id": fid, "clear_reason": "again"})


async def test_freeze_active_unique_constraint(db_path: str) -> None:
    await _make_company(db_path)
    await _make_freeze(db_path, "c1", "openai", "run-1")
    with pytest.raises(aiosqlite.IntegrityError):
        await _make_freeze(db_path, "c1", "openai", "run-2")


# ── credential broker ──


async def test_credential_roundtrip_and_isolation(methods: ProviderMethods, db_path: str) -> None:
    await methods._credential_set({
        "company_id": "c1", "provider_id": "openai", "credential_slot": "default",
        "credential": "sk-c1",
    })
    await methods._credential_set({
        "company_id": "c2", "provider_id": "openai", "credential_slot": "default",
        "credential": "sk-c2",
    })
    r1 = await methods._credential_get({"company_id": "c1", "provider_id": "openai"})
    r2 = await methods._credential_get({"company_id": "c2", "provider_id": "openai"})
    assert r1["credential"] == "sk-c1"
    assert r2["credential"] == "sk-c2"


async def test_credential_revoke(methods: ProviderMethods, db_path: str) -> None:
    await methods._credential_set({
        "company_id": "c1", "provider_id": "openai", "credential_slot": "default",
        "credential": "sk-c1",
    })
    await methods._credential_revoke({"company_id": "c1", "provider_id": "openai"})
    with pytest.raises(AcosError):
        await methods._credential_get({"company_id": "c1", "provider_id": "openai"})


async def test_credential_get_unknown_fail_closed(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._credential_get({"company_id": "c1", "provider_id": "openai"})


# ── runtime.* 驱动 FakeProviderAdapter ──


async def test_runtime_start_send_cancel(methods: ProviderMethods, db_path: str) -> None:
    await _make_company(db_path)
    started = await methods._runtime_start({"company_id": "c1", "model": "fake-model-1"})
    session_id = started["session_id"]
    assert session_id.startswith("rs-")

    sent = await methods._runtime_send({"session_id": session_id, "message": "hello"})
    assert sent["status"] == "completed"
    assert any(e["event_type"] == "message" for e in sent["events"])
    # 事件被 stamp 了 run_id
    assert all(e["run_id"] == sent["run_id"] for e in sent["events"])

    cancelled = await methods._runtime_cancel({"run_id": sent["run_id"]})
    assert cancelled["ok"] is True


async def test_runtime_send_unknown_session(methods: ProviderMethods) -> None:
    with pytest.raises(AcosError):
        await methods._runtime_send({"session_id": "rs-nope", "message": "x"})
