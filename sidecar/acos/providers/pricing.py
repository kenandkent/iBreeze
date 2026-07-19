"""版本化价格解析与最坏成本整数算法（设计方案 §6.11 / §10.6）。

金额一律 int64 micros（每百万 token 单价）。resolve_price 对未知、过期、跨公司、
币种冲突、负数或溢出 fail-closed。cost 用整数乘法后向上取整，不低估最坏成本。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

from acos.rpc.errors import AcosError

# int64 上界，超出即溢出 fail-closed
_INT64_MAX = 2**63 - 1
_PER_MILLION = 1_000_000

# 本地新增错误码（不改 errors.py）
PROV_PRICING_INVALID = "PROV-PRICING-INVALID"
PROV_PRICE_NOT_FOUND = "PROV-PRICE-NOT-FOUND"
PROV_PRICE_EXPIRED = "PROV-PRICE-EXPIRED"
PROV_PRICE_CURRENCY_CONFLICT = "PROV-PRICE-CURRENCY-CONFLICT"
PROV_PRICE_OVERFLOW = "PROV-PRICE-OVERFLOW"
PROV_PRICE_CROSS_COMPANY = "PROV-PRICE-CROSS-COMPANY"

_VALID_SOURCES = {"manual", "vendor_publication", "signed_catalog"}


@dataclass
class ResolvedPrice:
    pricing_version_id: str
    company_id: str
    provider_id: str
    model: str
    currency: str
    input_per_1m_micros: int
    output_per_1m_micros: int
    cache_per_1m_micros: int
    tool_call_flat_micros: int
    effective_at: str
    source: str
    verified_at: str


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str) -> datetime:
    """解析 RFC3339/ISO 时间为 aware datetime（UTC）。"""
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _check_int64(value: int) -> None:
    if value < 0 or value > _INT64_MAX:
        raise AcosError(
            code=PROV_PRICE_OVERFLOW,
            message="金额溢出 int64 或为负数",
            cause=f"value={value}",
            suggestion="检查价格版本或用量",
        )


def validate_pricing_fields(pricing: dict, source: str) -> tuple[int, int, int | None, int | None]:
    """校验 pricing DTO；返回规范化后的四个 micros 值。

    禁止 float、负数、非整数；source 必须合法；DTO 禁止传入 verified_at。
    """
    if source not in _VALID_SOURCES:
        raise AcosError(
            code=PROV_PRICING_INVALID,
            message="非法价格来源",
            cause=f"source={source}",
            suggestion=f"合法取值 {sorted(_VALID_SOURCES)}",
        )

    def _req_int(key: str) -> int:
        if key not in pricing:
            raise AcosError(PROV_PRICING_INVALID, f"缺少 {key}")
        v = pricing[key]
        if isinstance(v, bool) or not isinstance(v, int):
            raise AcosError(PROV_PRICING_INVALID, f"{key} 必须是整数 micros", cause=repr(v))
        if v < 0:
            raise AcosError(PROV_PRICING_INVALID, f"{key} 不能为负", cause=repr(v))
        _check_int64(v)
        return v

    def _opt_int(key: str) -> int | None:
        if key not in pricing or pricing[key] is None:
            return None
        v = pricing[key]
        if isinstance(v, bool) or not isinstance(v, int):
            raise AcosError(PROV_PRICING_INVALID, f"{key} 必须是整数 micros", cause=repr(v))
        if v < 0:
            raise AcosError(PROV_PRICING_INVALID, f"{key} 不能为负", cause=repr(v))
        _check_int64(v)
        return v

    input_p = _req_int("input_per_1m_micros")
    output_p = _req_int("output_per_1m_micros")
    cache_p = _opt_int("cache_per_1m_micros")
    tool_p = _opt_int("tool_call_flat_micros")
    return input_p, output_p, cache_p, tool_p


async def resolve_price(
    conn: aiosqlite.Connection,
    company_id: str,
    provider_id: str,
    model: str,
    currency: str,
    at: str | None = None,
) -> ResolvedPrice:
    """解析在 `at`（默认当前 UTC）时点生效的最新价格版本。

    fail-closed：
    - 未知（无任何价格行）→ PROV-PRICE-NOT-FOUND
    - 该币种无生效版本但存在其他币种 → PROV-PRICE-CURRENCY-CONFLICT
    - 请求时点早于所有 effective_at → PROV-PRICE-EXPIRED（尚未生效同样拒绝）
    """
    if not company_id or not provider_id or not model or not currency:
        raise AcosError(PROV_PRICING_INVALID, "resolve_price 参数不完整")

    at_dt = _parse_ts(at) if at else datetime.now(timezone.utc)

    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """SELECT * FROM provider_model_prices
           WHERE company_id = ? AND provider_id = ? AND model = ?
           ORDER BY effective_at DESC""",
        (company_id, provider_id, model),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        raise AcosError(
            code=PROV_PRICE_NOT_FOUND,
            message="未知模型价格",
            cause=f"{company_id}/{provider_id}/{model}",
            suggestion="先通过 provider.pricingPolicy.update 登记价格",
        )

    same_currency = [r for r in rows if r["currency"] == currency]
    if not same_currency:
        raise AcosError(
            code=PROV_PRICE_CURRENCY_CONFLICT,
            message="无该币种的价格版本",
            cause=f"requested={currency}, available={sorted({r['currency'] for r in rows})}",
        )

    effective = [r for r in same_currency if _parse_ts(r["effective_at"]) <= at_dt]
    if not effective:
        raise AcosError(
            code=PROV_PRICE_EXPIRED,
            message="请求时点无生效价格版本",
            cause=f"at={at_dt.isoformat()}",
            suggestion="检查 effective_at",
        )

    effective.sort(key=lambda r: _parse_ts(r["effective_at"]), reverse=True)
    r = effective[0]
    return ResolvedPrice(
        pricing_version_id=r["pricing_version_id"],
        company_id=r["company_id"],
        provider_id=r["provider_id"],
        model=r["model"],
        currency=r["currency"],
        input_per_1m_micros=int(r["input_per_1m_micros"]),
        output_per_1m_micros=int(r["output_per_1m_micros"]),
        cache_per_1m_micros=int(r["cache_per_1m_micros"] or 0),
        tool_call_flat_micros=int(r["tool_call_flat_micros"] or 0),
        effective_at=r["effective_at"],
        source=r["source"],
        verified_at=r["verified_at"],
    )


async def resolve_price_by_version(
    conn: aiosqlite.Connection,
    company_id: str,
    pricing_version_id: str,
) -> ResolvedPrice:
    """按固化的 pricing_version_id 复算历史 run；同时校验 company 隔离。"""
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        "SELECT * FROM provider_model_prices WHERE pricing_version_id = ?",
        (pricing_version_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise AcosError(PROV_PRICE_NOT_FOUND, "价格版本不存在", cause=pricing_version_id)
    r = dict(row)
    if r["company_id"] != company_id:
        raise AcosError(
            code=PROV_PRICE_CROSS_COMPANY,
            message="禁止跨公司复用价格版本",
            cause=f"price.company={r['company_id']} run.company={company_id}",
        )
    return ResolvedPrice(
        pricing_version_id=r["pricing_version_id"],
        company_id=r["company_id"],
        provider_id=r["provider_id"],
        model=r["model"],
        currency=r["currency"],
        input_per_1m_micros=int(r["input_per_1m_micros"]),
        output_per_1m_micros=int(r["output_per_1m_micros"]),
        cache_per_1m_micros=int(r["cache_per_1m_micros"] or 0),
        tool_call_flat_micros=int(r["tool_call_flat_micros"] or 0),
        effective_at=r["effective_at"],
        source=r["source"],
        verified_at=r["verified_at"],
    )


def _ceil_div(numerator: int, denominator: int) -> int:
    """整数向上取整除法（numerator, denominator 均 >= 0）。"""
    if denominator <= 0:
        raise AcosError(PROV_PRICING_INVALID, "除数非法")
    return -(-numerator // denominator)


def compute_cost_micros(
    price: ResolvedPrice,
    input_tokens: int,
    output_tokens: int,
    cache_tokens: int = 0,
    tool_call_count: int = 0,
) -> int:
    """按锁定价格版本用整数乘法后对最坏成本向上取整，检查 int64 溢出。

    单价单位为“每百万 token 的 micros”，故 cost = ceil(tokens * per_1m / 1_000_000)。
    """
    for t in (input_tokens, output_tokens, cache_tokens, tool_call_count):
        if isinstance(t, bool) or not isinstance(t, int) or t < 0:
            raise AcosError(PROV_PRICING_INVALID, "用量必须是非负整数", cause=repr(t))

    total = 0
    for tokens, per_1m in (
        (input_tokens, price.input_per_1m_micros),
        (output_tokens, price.output_per_1m_micros),
        (cache_tokens, price.cache_per_1m_micros),
    ):
        product = tokens * per_1m
        _check_int64(product)
        component = _ceil_div(product, _PER_MILLION)
        total += component
        _check_int64(total)

    tool_cost = tool_call_count * price.tool_call_flat_micros
    _check_int64(tool_cost)
    total += tool_cost
    _check_int64(total)
    return total


def new_pricing_version_id() -> str:
    return f"pv-{uuid.uuid4().hex}"


def server_verified_at() -> str:
    """服务端在校验并落库时写当前 UTC；DTO 禁止传入。"""
    return _now_utc()
