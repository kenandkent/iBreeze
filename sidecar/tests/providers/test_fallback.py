"""Provider fallback chain / probe_all / dissolve / eligibility tests."""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite
import pytest

from acos.providers.base import AvailabilityStatus, ProviderAdapter
from acos.providers.registry import ProviderRegistry
from acos.store.migrator import Migrator


class _StubDriver(ProviderAdapter):
    """可控的 Provider stub，可切换 available 状态。"""

    def __init__(self, available: bool = True) -> None:
        self._available = available

    async def check_availability(self) -> AvailabilityStatus:
        return AvailabilityStatus(available=self._available, reason="ok" if self._available else "unreachable")

    async def capabilities(self):  # type: ignore[override]
        return None

    async def send(self, session, message, stream=False):  # type: ignore[override]
        return {}

    async def cancel(self, run_id: str) -> bool:
        return True

    async def health_check(self) -> dict:
        return {"healthy": self._available}


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = tmp_path / "test.db"
    migrator = Migrator(str(p))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(p)


async def _make_company(db_path: str, company_id: str, policy: dict | None = None) -> None:
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute(
            """INSERT INTO companies
               (company_id, name, status, default_provider_policy, default_budget_policy, version)
               VALUES (?, ?, 'active', ?, '{}', 1)""",
            (company_id, f"Company {company_id}", json.dumps(policy or {})),
        )
        await conn.commit()
    finally:
        await conn.close()


async def _insert_availability(
    db_path: str, company_id: str, provider_id: str, available: bool = True, reason: str = ""
) -> None:
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute(
            """INSERT INTO provider_availability
               (company_id, provider_id, available, healthy, reason, version)
               VALUES (?, ?, ?, 1, ?, 1)""",
            (company_id, provider_id, 1 if available else 0, reason),
        )
        await conn.commit()
    finally:
        await conn.close()


async def _insert_model(
    db_path: str,
    provider_id: str,
    model: str,
    company_id: str | None = None,
    billing_mode: str = "unknown",
    enforces_output_cap: bool = False,
) -> None:
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute(
            """INSERT INTO provider_models
               (model_id, provider_id, model, display_name, supports,
                owner_company_id, source, manifest_version, config_version,
                tier, billing_mode, enforces_output_cap, context_window, latency_hint)
               VALUES (?, ?, ?, ?, '[]', ?, 'test', '1', 1, 'standard', ?, ?, 0, '')""",
            (
                f"pm-{provider_id}-{model}",
                provider_id,
                model,
                model,
                company_id,
                billing_mode,
                1 if enforces_output_cap else 0,
            ),
        )
        await conn.commit()
    finally:
        await conn.close()


# ── probe_all ───────────────────────────────────────────────


async def test_probe_all_probes_all_configured_providers(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "driver-a")
    await _insert_availability(db_path, "c1", "driver-b")

    registry = ProviderRegistry(db_path)
    registry.register_driver("driver-a", _StubDriver(available=True))
    registry.register_driver("driver-b", _StubDriver(available=False))

    result = await registry.probe_all("c1")
    assert result["probed"] == 2
    assert result["results"]["driver-a"]["available"] is True
    assert result["results"]["driver-b"]["available"] is False


async def test_probe_all_no_providers(db_path: str) -> None:
    await _make_company(db_path, "c1")
    registry = ProviderRegistry(db_path)
    result = await registry.probe_all("c1")
    assert result["probed"] == 0
    assert result["results"] == {}


# ── resolve_provider ────────────────────────────────────────


async def test_resolve_provider_override_takes_priority(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "prov-override")
    await _insert_availability(db_path, "c1", "prov-template")
    await _insert_availability(db_path, "c1", "prov-policy")

    registry = ProviderRegistry(db_path)

    result = await registry.resolve_provider(
        "c1",
        provider_override={"provider_id": "prov-override", "model": "m1"},
        template_provider={"provider_id": "prov-template", "model": "m2"},
    )
    assert result["level"] == "override"
    assert result["provider_id"] == "prov-override"


async def test_resolve_provider_fallback_to_template(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "prov-override", available=False)
    await _insert_availability(db_path, "c1", "prov-template")

    registry = ProviderRegistry(db_path)

    result = await registry.resolve_provider(
        "c1",
        provider_override={"provider_id": "prov-override", "model": "m1"},
        template_provider={"provider_id": "prov-template", "model": "m2"},
    )
    assert result["level"] == "template"
    assert result["provider_id"] == "prov-template"


async def test_resolve_provider_fallback_to_policy(db_path: str) -> None:
    policy = {
        "standard": {"provider_id": "prov-policy", "model": "m3"},
    }
    await _make_company(db_path, "c1", policy)
    await _insert_availability(db_path, "c1", "prov-policy")

    registry = ProviderRegistry(db_path)

    result = await registry.resolve_provider("c1")
    assert result["level"] == "policy"
    assert result["provider_id"] == "prov-policy"
    assert result["model"] == "m3"


async def test_resolve_provider_all_unavailable_returns_none(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "prov-a", available=False)

    registry = ProviderRegistry(db_path)

    result = await registry.resolve_provider(
        "c1",
        provider_override={"provider_id": "prov-a", "model": "m1"},
    )
    assert result["level"] == "none"
    assert result["reason"] == "all_unavailable"


async def test_resolve_provider_policy_fallback_to_standard_tier(db_path: str) -> None:
    policy = {
        "free": {"provider_id": "prov-free", "model": "free-m"},
        "standard": {"provider_id": "prov-std", "model": "std-m"},
    }
    await _make_company(db_path, "c1", policy)
    await _insert_availability(db_path, "c1", "prov-std")

    registry = ProviderRegistry(db_path)

    result = await registry.resolve_provider("c1", requested_tier="premium")
    assert result["level"] == "policy"
    assert result["provider_id"] == "prov-std"


# ── check_provider_eligible ─────────────────────────────────


async def test_check_provider_eligible_model_not_found(db_path: str) -> None:
    await _make_company(db_path, "c1")
    registry = ProviderRegistry(db_path)

    result = await registry.check_provider_eligible("c1", "openai", "nonexistent")
    assert result["eligible"] is False
    assert result["reason"] == "model_not_found"


async def test_check_provider_eligible_hard_budget_filters_not_metered(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "openai")
    await _insert_model(
        db_path, "openai", "gpt-4o", "c1",
        billing_mode="flat_rate", enforces_output_cap=True,
    )
    registry = ProviderRegistry(db_path)

    result = await registry.check_provider_eligible("c1", "openai", "gpt-4o", hard_budget=True)
    assert result["eligible"] is False
    assert result["reason"] == "not_metered"


async def test_check_provider_eligible_hard_budget_filters_no_output_cap(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "openai")
    await _insert_model(
        db_path, "openai", "gpt-4o", "c1",
        billing_mode="metered", enforces_output_cap=False,
    )
    registry = ProviderRegistry(db_path)

    result = await registry.check_provider_eligible("c1", "openai", "gpt-4o", hard_budget=True)
    assert result["eligible"] is False
    assert result["reason"] == "no_output_cap"


async def test_check_provider_eligible_hard_budget_passes(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "openai")
    await _insert_model(
        db_path, "openai", "gpt-4o", "c1",
        billing_mode="metered", enforces_output_cap=True,
    )
    registry = ProviderRegistry(db_path)

    result = await registry.check_provider_eligible("c1", "openai", "gpt-4o", hard_budget=True)
    assert result["eligible"] is True
    assert result["reason"] == "ok"


async def test_check_provider_eligible_unavailable_freeze(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "openai", available=False, reason="frozen_by_dissolution")
    await _insert_model(db_path, "openai", "gpt-4o", "c1")
    registry = ProviderRegistry(db_path)

    result = await registry.check_provider_eligible("c1", "openai", "gpt-4o")
    assert result["eligible"] is False
    assert "unavailable" in result["reason"]


# ── dissolution_provider_consumer ────────────────────────────


async def test_dissolution_provider_consumer_freezes_all(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "prov-a", available=True)
    await _insert_availability(db_path, "c1", "prov-b", available=True)

    registry = ProviderRegistry(db_path)
    await registry.dissolution_provider_consumer("c1")

    avail_a = await registry.get_availability("c1", "prov-a")
    avail_b = await registry.get_availability("c1", "prov-b")
    assert avail_a is not None
    assert avail_b is not None
    assert avail_a["available"] == 0
    assert avail_b["available"] == 0
    assert avail_a["reason"] == "frozen_by_dissolution"
    assert avail_b["reason"] == "frozen_by_dissolution"


async def test_dissolution_provider_consumer_idempotent(db_path: str) -> None:
    await _make_company(db_path, "c1")
    await _insert_availability(db_path, "c1", "prov-a", available=True)

    registry = ProviderRegistry(db_path)
    await registry.dissolution_provider_consumer("c1")
    # Second call is idempotent
    await registry.dissolution_provider_consumer("c1")

    avail = await registry.get_availability("c1", "prov-a")
    assert avail is not None
    assert avail["available"] == 0
