"""价格解析与最坏成本整数算法测试（P6-T1a）。"""

from __future__ import annotations

import uuid
from pathlib import Path

import aiosqlite
import pytest

from acos.providers import pricing as pm
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


async def _insert_price(
    db_path: str,
    company_id: str,
    provider_id: str,
    model: str,
    currency: str,
    effective_at: str,
    input_p: int = 1_000_000,
    output_p: int = 2_000_000,
    cache_p: int | None = None,
    tool_p: int | None = None,
) -> str:
    pv = pm.new_pricing_version_id()
    conn = await aiosqlite.connect(db_path)
    try:
        await conn.execute(
            """INSERT INTO provider_model_prices
               (pricing_version_id, company_id, provider_id, model,
                input_per_1m_micros, output_per_1m_micros, cache_per_1m_micros,
                tool_call_flat_micros, currency, effective_at, source, verified_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)""",
            (pv, company_id, provider_id, model, input_p, output_p, cache_p, tool_p,
             currency, effective_at, pm.server_verified_at()),
        )
        await conn.commit()
    finally:
        await conn.close()
    return pv


# ── resolve_price 边界 ──


async def test_resolve_effective_boundary(db_path: str) -> None:
    await _insert_price(db_path, "c1", "openai", "gpt-4o", "USD", "2026-01-01T00:00:00Z")
    conn = await aiosqlite.connect(db_path)
    try:
        # 生效时点之后可解析
        price = await pm.resolve_price(conn, "c1", "openai", "gpt-4o", "USD", "2026-06-01T00:00:00Z")
        assert price.input_per_1m_micros == 1_000_000
        # 生效时点之前拒绝
        with pytest.raises(AcosError) as ei:
            await pm.resolve_price(conn, "c1", "openai", "gpt-4o", "USD", "2025-06-01T00:00:00Z")
        assert ei.value.code == pm.PROV_PRICE_EXPIRED
    finally:
        await conn.close()


async def test_resolve_picks_latest_version(db_path: str) -> None:
    await _insert_price(db_path, "c1", "openai", "gpt-4o", "USD", "2026-01-01T00:00:00Z", input_p=1_000_000)
    pv2 = await _insert_price(db_path, "c1", "openai", "gpt-4o", "USD", "2026-03-01T00:00:00Z", input_p=1_500_000)
    conn = await aiosqlite.connect(db_path)
    try:
        price = await pm.resolve_price(conn, "c1", "openai", "gpt-4o", "USD", "2026-06-01T00:00:00Z")
        assert price.pricing_version_id == pv2
        assert price.input_per_1m_micros == 1_500_000
    finally:
        await conn.close()


async def test_resolve_unknown_fail_closed(db_path: str) -> None:
    conn = await aiosqlite.connect(db_path)
    try:
        with pytest.raises(AcosError) as ei:
            await pm.resolve_price(conn, "c1", "openai", "nope", "USD")
        assert ei.value.code == pm.PROV_PRICE_NOT_FOUND
    finally:
        await conn.close()


async def test_resolve_currency_conflict(db_path: str) -> None:
    await _insert_price(db_path, "c1", "openai", "gpt-4o", "USD", "2026-01-01T00:00:00Z")
    conn = await aiosqlite.connect(db_path)
    try:
        with pytest.raises(AcosError) as ei:
            await pm.resolve_price(conn, "c1", "openai", "gpt-4o", "EUR", "2026-06-01T00:00:00Z")
        assert ei.value.code == pm.PROV_PRICE_CURRENCY_CONFLICT
    finally:
        await conn.close()


async def test_resolve_cross_company_isolation(db_path: str) -> None:
    await _insert_price(db_path, "c1", "openai", "gpt-4o", "USD", "2026-01-01T00:00:00Z")
    conn = await aiosqlite.connect(db_path)
    try:
        # c2 无价格 → 不回退到 c1
        with pytest.raises(AcosError) as ei:
            await pm.resolve_price(conn, "c2", "openai", "gpt-4o", "USD", "2026-06-01T00:00:00Z")
        assert ei.value.code == pm.PROV_PRICE_NOT_FOUND
    finally:
        await conn.close()


async def test_resolve_by_version_cross_company_denied(db_path: str) -> None:
    pv = await _insert_price(db_path, "c1", "openai", "gpt-4o", "USD", "2026-01-01T00:00:00Z")
    conn = await aiosqlite.connect(db_path)
    try:
        # 历史复算：同公司 OK
        price = await pm.resolve_price_by_version(conn, "c1", pv)
        assert price.pricing_version_id == pv
        # 跨公司复算拒绝
        with pytest.raises(AcosError) as ei:
            await pm.resolve_price_by_version(conn, "c2", pv)
        assert ei.value.code == pm.PROV_PRICE_CROSS_COMPANY
    finally:
        await conn.close()


# ── validate_pricing_fields ──


def test_validate_rejects_negative() -> None:
    with pytest.raises(AcosError):
        pm.validate_pricing_fields({"input_per_1m_micros": -1, "output_per_1m_micros": 1}, "manual")


def test_validate_rejects_float() -> None:
    with pytest.raises(AcosError):
        pm.validate_pricing_fields({"input_per_1m_micros": 1.5, "output_per_1m_micros": 1}, "manual")


def test_validate_rejects_bad_source() -> None:
    with pytest.raises(AcosError):
        pm.validate_pricing_fields({"input_per_1m_micros": 1, "output_per_1m_micros": 1}, "bogus")


def test_validate_rejects_overflow() -> None:
    with pytest.raises(AcosError):
        pm.validate_pricing_fields(
            {"input_per_1m_micros": 2**63, "output_per_1m_micros": 1}, "manual"
        )


# ── compute_cost_micros 向上取整 / 溢出 ──


def _price(**kw) -> pm.ResolvedPrice:
    base = dict(
        pricing_version_id="pv", company_id="c1", provider_id="p", model="m", currency="USD",
        input_per_1m_micros=1_000_000, output_per_1m_micros=2_000_000,
        cache_per_1m_micros=0, tool_call_flat_micros=0,
        effective_at="2026-01-01T00:00:00Z", source="manual", verified_at="2026-01-01T00:00:00Z",
    )
    base.update(kw)
    return pm.ResolvedPrice(**base)


def test_cost_ceil_rounds_up() -> None:
    # 1 token @ 1_000_000 micros/1M = 1_000_000/1_000_000 = 1 -> ceil(1)=1
    price = _price(input_per_1m_micros=1_000_000, output_per_1m_micros=0)
    assert pm.compute_cost_micros(price, input_tokens=1, output_tokens=0) == 1
    # 1 token @ 1_500_000/1M = 1.5 -> ceil = 2（不低估最坏成本）
    price2 = _price(input_per_1m_micros=1_500_000, output_per_1m_micros=0)
    assert pm.compute_cost_micros(price2, input_tokens=1, output_tokens=0) == 2
    # 3 tokens @ 1/1M = 0.000003 -> ceil = 1
    price3 = _price(input_per_1m_micros=1, output_per_1m_micros=0)
    assert pm.compute_cost_micros(price3, input_tokens=3, output_tokens=0) == 1


def test_cost_sums_components() -> None:
    price = _price(
        input_per_1m_micros=1_000_000, output_per_1m_micros=2_000_000,
        cache_per_1m_micros=500_000, tool_call_flat_micros=100,
    )
    # input: 1M tokens -> 1_000_000 ; output: 1M -> 2_000_000 ; cache 1M -> 500_000 ; 2 tools -> 200
    cost = pm.compute_cost_micros(price, 1_000_000, 1_000_000, 1_000_000, 2)
    assert cost == 1_000_000 + 2_000_000 + 500_000 + 200


def test_cost_rejects_negative_usage() -> None:
    price = _price()
    with pytest.raises(AcosError):
        pm.compute_cost_micros(price, input_tokens=-1, output_tokens=0)


def test_cost_rejects_overflow() -> None:
    price = _price(input_per_1m_micros=pm._INT64_MAX)
    with pytest.raises(AcosError) as ei:
        pm.compute_cost_micros(price, input_tokens=10**12, output_tokens=0)
    assert ei.value.code == pm.PROV_PRICE_OVERFLOW
