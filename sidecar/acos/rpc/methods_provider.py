"""Provider 命名空间 RPC 方法集合（provider.*）。

对照设计方案附录 B provider.* 段与 §6.11。写方法注入 LocalOwner，
DTO 禁止传入 verified_at（服务端注入），历史价格版本禁止覆盖，
tierMapping 用 Company version CAS。runtime.* 驱动 FakeProviderAdapter（可测桩）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite
import httpx

from acos.organization.principal import get_local_owner
from acos.providers import pricing as pricing_mod
from acos.providers.credential_broker import CredentialBroker
from acos.providers.fake import FakeProviderAdapter
from acos.providers.registry import ProviderRegistry, load_manifest
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer
from acos.runtime.adapter import AgentRuntime

# 本地新增错误码（不改 errors.py）
PROV_VALIDATION = "PROV-VALIDATION"
PROV_FREEZE_NOT_FOUND = "PROV-FREEZE-NOT-FOUND"
PROV_FREEZE_STILL_UNSAFE = "PROV-FREEZE-STILL-UNSAFE"
ORG_VALIDATION = "ORG-VALIDATION"
SYS_OPTIMISTIC_LOCK_CONFLICT = "SYS-OPTIMISTIC-LOCK-CONFLICT"

_TIER_KEYS = ("free", "standard", "premium")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProviderMethods:
    """provider.* RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._registry = ProviderRegistry(db_path)
        self._broker = CredentialBroker(db_path)
        self._runtime = AgentRuntime(db_path)
        # runtime.* 默认驱动 FakeProviderAdapter（可测桩，不调真实 CLI/API）
        self._fake = FakeProviderAdapter()
        self._registry.register_driver("fake", self._fake)

    def register_to(self, server: RPCServer) -> None:
        server.register_method("provider.list", self._provider_list)
        server.register_method("provider.create", self._provider_create)
        server.register_method("provider.agent.list", self._agent_list)
        server.register_method("provider.models.fetch", self._models_fetch)
        server.register_method("provider.model.list", self._model_list)
        server.register_method("provider.pricingPolicy.update", self._pricing_policy_update)
        server.register_method("provider.budgetFreeze.clear", self._budget_freeze_clear)
        server.register_method("provider.tierMapping.update", self._tier_mapping_update)
        server.register_method("provider.probe", self._probe)
        server.register_method("provider.credential.get", self._credential_get)
        server.register_method("provider.credential.set", self._credential_set)
        server.register_method("provider.credential.revoke", self._credential_revoke)
        server.register_method("provider.runtime.start", self._runtime_start)
        server.register_method("provider.runtime.send", self._runtime_send)
        server.register_method("provider.runtime.cancel", self._runtime_cancel)

    async def ensure_manifest_imported(self) -> dict:
        """幂等导入内置 manifest（供接线时调用一次）。"""
        return await self._registry.import_manifest()

    # ── 连接与 LocalOwner ────────────────────────────────

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def _require_local_owner(self, conn: aiosqlite.Connection) -> str:
        owner = await get_local_owner(conn)
        return owner.owner_id

    # ── provider.list ────────────────────────────────────

    async def _provider_list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(PROV_VALIDATION, "缺少 company_id")

        await self._ensure_manifest()

        conn = await self._connect()
        try:
            cur = await conn.execute("SELECT * FROM providers ORDER BY provider_id")
            providers = [dict(r) for r in await cur.fetchall()]

            tier_mapping = await self._get_tier_mapping(conn, company_id)

            items = []
            for p in providers:
                avail = await self._registry.get_availability(company_id, p["provider_id"])
                items.append({
                    "provider_id": p["provider_id"],
                    "name": p["name"],
                    "provider_type": p["provider_type"],
                    "status": p.get("status", "active"),
                    "availability": (
                        {
                            "available": bool(avail["available"]),
                            "healthy": bool(avail["healthy"]),
                            "reason": avail["reason"],
                            "probed_at": avail["probed_at"],
                        }
                        if avail else None
                    ),
                })
            return {"items": items, "tier_mapping": tier_mapping}
        finally:
            await conn.close()

    # ── provider.create ─────────────────────────────────

    # 固定的 cli agent（调用本机 agent 工具），后续迭代可扩展
    # models 为内置兜底清单（无 key 时展示）；claude-code 走 Anthropic 官方固定清单
    _CLI_AGENTS = {
        "cursor-cli": {
            "display_name": "Cursor CLI",
            "vendor": None,
            "models": [{"model": "auto", "display_name": "Auto (Cursor 自动选择)"}],
        },
        "claude-code": {
            "display_name": "Claude Code",
            "vendor": "anthropic",
            "models": [
                {"model": "claude-sonnet-5", "display_name": "Claude Sonnet 5"},
                {"model": "claude-opus-4-8", "display_name": "Claude Opus 4.8"},
            ],
        },
        "codex-cli": {
            "display_name": "Codex CLI",
            "vendor": "openai",
            "models": [
                {"model": "gpt-5.1-codex", "display_name": "GPT-5.1 Codex"},
                {"model": "gpt-5-codex", "display_name": "GPT-5 Codex"},
                {"model": "codex-mini-latest", "display_name": "Codex Mini (latest)"},
            ],
        },
        "opencode": {
            "display_name": "OpenCode",
            "vendor": "multi",
            "models": [
                {"model": "anthropic/claude-sonnet-5", "display_name": "Anthropic / Claude Sonnet 5"},
                {"model": "anthropic/claude-opus-4-8", "display_name": "Anthropic / Claude Opus 4.8"},
                {"model": "openai/gpt-5.1-codex", "display_name": "OpenAI / GPT-5.1 Codex"},
                {"model": "google/gemini-2.5-pro", "display_name": "Google / Gemini 2.5 Pro"},
            ],
        },
    }

    # API Key 形式可选择的供应商及其默认 base_url
    _API_VENDORS = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com",
        "anthropic": "https://api.anthropic.com/v1",
        # 第三方必须用户自己填 base_url，无默认值
        "third_party": "",
    }

    async def _provider_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        provider_type = params.get("provider_type", "openai")
        if not name:
            raise AcosError(PROV_VALIDATION, "缺少 name")
        if provider_type not in ("api", "cli"):
            raise AcosError(PROV_VALIDATION, "provider_type 仅支持 api / cli")

        config = params.get("config")
        if config is not None and not isinstance(config, dict):
            raise AcosError(PROV_VALIDATION, "config 必须为对象")
        config = dict(config or {})

        if provider_type == "cli":
            agent = config.get("agent")
            if agent not in self._CLI_AGENTS:
                raise AcosError(PROV_VALIDATION, f"cli agent 仅支持 {list(self._CLI_AGENTS.keys())}")
            model = config.get("model")
            if not model:
                raise AcosError(PROV_VALIDATION, "cli provider 必须指定 model")
            config = {"agent": agent, "model": model}
        elif provider_type == "api":
            # api 形式：凭证走 Keychain（provider.credential.set），此处仅存连接配置 + 供应商标识
            base_url = config.get("base_url")
            if base_url is not None and not isinstance(base_url, str):
                raise AcosError(PROV_VALIDATION, "base_url 必须为字符串")
            api_vendor = config.get("api_vendor")
            if api_vendor is not None and api_vendor not in self._API_VENDORS and api_vendor != "third_party":
                raise AcosError(PROV_VALIDATION, f"api_vendor 仅支持 {list(self._API_VENDORS.keys()) + ['third_party']}")
            config = {"base_url": base_url} if base_url else {}
            if api_vendor:
                config["api_vendor"] = api_vendor

        provider_id = params.get("provider_id") or f"pv-{uuid.uuid4().hex[:12]}"
        now = _now_utc()

        conn = await self._connect()
        try:
            await conn.execute(
                """INSERT INTO providers
                   (provider_id, name, provider_type, status, config, created_at)
                   VALUES (?, ?, ?, 'active', ?, ?)""",
                (provider_id, name, provider_type, json.dumps(config, ensure_ascii=False), now),
            )
            await conn.commit()
        finally:
            await conn.close()

        return {"provider_id": provider_id, "name": name, "provider_type": provider_type, "status": "active"}

    # ── provider.agent.list ─────────────────────────────

    async def _agent_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """返回固定的 cli agent 及其支持的模型（供 UI 下拉）。"""
        agents = [
            {
                "agent_id": aid,
                "display_name": meta["display_name"],
                "models": meta["models"],
            }
            for aid, meta in self._CLI_AGENTS.items()
        ]
        return {"agents": agents}

    # ── provider.models.fetch ───────────────────────────
    # 实时调用厂商官方 API 拉取可用模型（需 api_key）。失败则降级到内置兜底清单。

    async def _models_fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        vendor = params.get("api_vendor")
        api_key = params.get("api_key") or ""
        base_url = (params.get("base_url") or "").strip()

        # 兜底清单（无 key / 调用失败时使用）
        fallback = self._vendor_fallback_models(vendor)

        if not api_key:
            return {"models": fallback, "source": "fallback", "error_message": "缺少 api_key，使用内置清单"}

        try:
            models = await self._fetch_vendor_models(vendor, api_key, base_url)
            if not models:
                return {"models": fallback, "source": "fallback", "error_message": "厂商返回为空，使用内置清单"}
            return {"models": models, "source": "live"}
        except Exception as exc:  # 网络/鉴权失败均降级
            return {"models": fallback, "source": "fallback", "error_message": str(exc)}

    def _vendor_fallback_models(self, vendor: str | None) -> list[dict[str, str]]:
        if vendor == "anthropic":
            return [
                {"model": "claude-sonnet-5", "display_name": "Claude Sonnet 5"},
                {"model": "claude-opus-4-8", "display_name": "Claude Opus 4.8"},
            ]
        if vendor in ("openai", "deepseek", "third_party"):
            return [
                {"model": "gpt-5.1-codex", "display_name": "GPT-5.1 Codex"},
                {"model": "gpt-5-codex", "display_name": "GPT-5 Codex"},
                {"model": "gpt-4o", "display_name": "GPT-4o"},
            ]
        return []

    async def _fetch_vendor_models(
        self, vendor: str | None, api_key: str, base_url: str
    ) -> list[dict[str, str]]:
        if vendor == "anthropic":
            url = "https://api.anthropic.com/v1/models"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json().get("data", [])
                return [
                    {"model": m["id"], "display_name": m.get("display_name") or m["id"]}
                    for m in data
                ]
        # openai / deepseek 走 OpenAI 格式 /v1/models；third_party 必须用户提供 base_url
        if vendor == "third_party":
            if not base_url:
                raise AcosError(PROV_VALIDATION, "第三方供应商必须提供 Base URL")
            base = base_url
        else:
            base = base_url or self._API_VENDORS.get(vendor or "", "https://api.openai.com/v1")
        if not base.endswith("/models"):
            base = base.rstrip("/") + "/models"
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(base, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return [{"model": m["id"], "display_name": m["id"]} for m in data]

    # ── provider.model.list ──────────────────────────────

    async def _model_list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(PROV_VALIDATION, "缺少 company_id")
        provider_id = params.get("provider_id")

        await self._ensure_manifest()

        conn = await self._connect()
        try:
            # 全局内置模型 (owner_company_id IS NULL) + 该公司私有模型
            sql = (
                "SELECT * FROM provider_models "
                "WHERE (owner_company_id IS NULL OR owner_company_id = ?)"
            )
            args: list[Any] = [company_id]
            if provider_id:
                sql += " AND provider_id = ?"
                args.append(provider_id)
            sql += " ORDER BY provider_id, model"
            cur = await conn.execute(sql, args)
            rows = [dict(r) for r in await cur.fetchall()]

            items = []
            for r in rows:
                price_summary = await self._latest_price_summary(conn, company_id, r["provider_id"], r["model"])
                items.append({
                    "provider_id": r["provider_id"],
                    "model": r["model"],
                    "display_name": r["display_name"],
                    "source": r["source"],
                    "tier": r["tier"],
                    "billing_mode": r["billing_mode"],
                    "enforces_output_cap": bool(r["enforces_output_cap"]),
                    "context_window": r["context_window"],
                    "supports": json.loads(r["supports"]),
                    "is_company_private": r["owner_company_id"] is not None,
                    "price": price_summary,
                })
            return {"items": items}
        finally:
            await conn.close()

    async def _latest_price_summary(
        self, conn: aiosqlite.Connection, company_id: str, provider_id: str, model: str
    ) -> dict | None:
        cur = await conn.execute(
            """SELECT * FROM provider_model_prices
               WHERE company_id = ? AND provider_id = ? AND model = ?
               ORDER BY effective_at DESC LIMIT 1""",
            (company_id, provider_id, model),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        r = dict(row)
        return {
            "pricing_version_id": r["pricing_version_id"],
            "currency": r["currency"],
            "input_per_1m_micros": r["input_per_1m_micros"],
            "output_per_1m_micros": r["output_per_1m_micros"],
            "cache_per_1m_micros": r["cache_per_1m_micros"],
            "tool_call_flat_micros": r["tool_call_flat_micros"],
            "effective_at": r["effective_at"],
        }

    # ── provider.pricingPolicy.update ────────────────────

    async def _pricing_policy_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        provider_id = params.get("provider_id")
        model = params.get("model")
        currency = params.get("currency")
        effective_at = params.get("effective_at")
        source = params.get("source")
        pricing = params.get("pricing")

        if not all([company_id, provider_id, model, currency, effective_at, source]):
            raise AcosError(pricing_mod.PROV_PRICING_INVALID, "价格更新参数不完整")
        if not isinstance(pricing, dict):
            raise AcosError(pricing_mod.PROV_PRICING_INVALID, "pricing 必须是对象")
        # DTO 禁止传入 verified_at
        if "verified_at" in params or "verified_at" in pricing:
            raise AcosError(pricing_mod.PROV_PRICING_INVALID, "verified_at 禁止由客户端传入")

        input_p, output_p, cache_p, tool_p = pricing_mod.validate_pricing_fields(pricing, source)
        # 校验 effective_at 可解析
        try:
            pricing_mod._parse_ts(effective_at)
        except Exception as exc:
            raise AcosError(pricing_mod.PROV_PRICING_INVALID, "effective_at 非法", cause=str(exc))

        conn = await self._connect()
        try:
            await self._require_local_owner(conn)

            model_spec = params.get("model_spec")
            if model_spec is not None:
                await self._register_company_model(conn, company_id, provider_id, model, model_spec)

            pricing_version_id = pricing_mod.new_pricing_version_id()
            verified_at = pricing_mod.server_verified_at()
            try:
                await conn.execute(
                    """INSERT INTO provider_model_prices
                       (pricing_version_id, company_id, provider_id, model,
                        input_per_1m_micros, output_per_1m_micros, cache_per_1m_micros,
                        tool_call_flat_micros, currency, effective_at, source, verified_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pricing_version_id, company_id, provider_id, model,
                     input_p, output_p, cache_p, tool_p, currency, effective_at, source, verified_at),
                )
            except aiosqlite.IntegrityError:
                # 历史版本禁止覆盖（同 effective_at 键冲突）
                raise AcosError(
                    pricing_mod.PROV_PRICING_INVALID,
                    "该 effective_at 已存在价格版本，历史不可覆盖",
                    cause=f"{provider_id}/{model}/{currency}/{effective_at}",
                )
            await conn.commit()
            return {"pricing_version_id": pricing_version_id, "verified_at": verified_at}
        finally:
            await conn.close()

    async def _register_company_model(
        self, conn: aiosqlite.Connection, company_id: str, provider_id: str, model: str, spec: dict
    ) -> None:
        """OpenAI-Compatible 私有模型：按 (owner_company_id,provider_id,model) 登记/更新静态能力。"""
        required = ("tier", "context_window", "supports", "billing_mode", "enforces_output_cap")
        for k in required:
            if k not in spec:
                raise AcosError(pricing_mod.PROV_PRICING_INVALID, f"model_spec 缺少 {k}")
        cur = await conn.execute(
            """SELECT model_id, config_version FROM provider_models
               WHERE owner_company_id = ? AND provider_id = ? AND model = ?""",
            (company_id, provider_id, model),
        )
        existing = await cur.fetchone()
        supports = json.dumps(spec["supports"])
        if existing is None:
            await conn.execute(
                """INSERT INTO provider_models
                   (model_id, provider_id, model, display_name, supports, owner_company_id,
                    source, config_version, tier, billing_mode, enforces_output_cap,
                    context_window, latency_hint)
                   VALUES (?, ?, ?, ?, ?, ?, 'company_custom', 1, ?, ?, ?, ?, ?)""",
                (f"pm-{uuid.uuid4().hex}", provider_id, model, spec.get("display_name", model),
                 supports, company_id, spec["tier"], spec["billing_mode"],
                 1 if spec["enforces_output_cap"] else 0, int(spec["context_window"]),
                 spec.get("latency_hint", "")),
            )
        else:
            await conn.execute(
                """UPDATE provider_models SET
                       supports = ?, tier = ?, billing_mode = ?, enforces_output_cap = ?,
                       context_window = ?, config_version = config_version + 1
                   WHERE model_id = ?""",
                (supports, spec["tier"], spec["billing_mode"],
                 1 if spec["enforces_output_cap"] else 0, int(spec["context_window"]),
                 existing[0]),
            )

    # ── provider.budgetFreeze.clear ──────────────────────

    async def _budget_freeze_clear(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        freeze_id = params.get("freeze_id")
        clear_reason = params.get("clear_reason")

        if not company_id or not freeze_id:
            raise AcosError(PROV_VALIDATION, "缺少 company_id/freeze_id")
        reason = (clear_reason or "").strip()
        if not (1 <= len(reason) <= 1000):
            raise AcosError(PROV_VALIDATION, "clear_reason 必须为 1..1000 字符")

        conn = await self._connect()
        try:
            owner_id = await self._require_local_owner(conn)

            cur = await conn.execute(
                """SELECT * FROM provider_budget_freezes
                   WHERE freeze_id = ? AND company_id = ?""",
                (freeze_id, company_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(PROV_FREEZE_NOT_FOUND, "冻结不存在", cause=freeze_id)
            r = dict(row)
            if r["status"] != "active":
                raise AcosError(PROV_FREEZE_NOT_FOUND, "冻结非 active，不可清除")

            # 安全条件：重新验价——该 provider 至少存在一个可解析的当前有效价格
            safe = await self._freeze_clear_safe(conn, company_id, r["provider_id"])
            if not safe:
                raise AcosError(
                    PROV_FREEZE_STILL_UNSAFE,
                    "解除条件未满足（无有效价格/未通过重新校验）",
                    suggestion="先重新 probe 并登记有效价格",
                )

            # active→cleared 用 version CAS
            expected_version = r["version"]
            cur2 = await conn.execute(
                """UPDATE provider_budget_freezes
                   SET status = 'cleared', cleared_at = ?, cleared_by = ?, clear_reason = ?,
                       version = version + 1
                   WHERE freeze_id = ? AND version = ? AND status = 'active'""",
                (_now_utc(), owner_id, reason, freeze_id, expected_version),
            )
            if cur2.rowcount != 1:
                raise AcosError(SYS_OPTIMISTIC_LOCK_CONFLICT, "并发清除冲突")
            await conn.commit()
            return {"ok": True, "freeze_id": freeze_id}
        finally:
            await conn.close()

    async def _freeze_clear_safe(
        self, conn: aiosqlite.Connection, company_id: str, provider_id: str
    ) -> bool:
        """重新验价：provider 下存在至少一个当前生效的价格版本。"""
        cur = await conn.execute(
            """SELECT model, currency FROM provider_model_prices
               WHERE company_id = ? AND provider_id = ?""",
            (company_id, provider_id),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            try:
                await pricing_mod.resolve_price(conn, company_id, provider_id, r["model"], r["currency"])
                return True
            except AcosError:
                continue
        return False

    # ── provider.tierMapping.update ──────────────────────

    async def _tier_mapping_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        expected_company_version = params.get("expected_company_version")
        tier = params.get("tier")
        provider_id = params.get("provider_id")
        model = params.get("model")

        if not company_id or expected_company_version is None or not tier:
            raise AcosError(ORG_VALIDATION, "tierMapping 参数不完整")
        if tier not in _TIER_KEYS:
            raise AcosError(ORG_VALIDATION, f"tier 必须是 {_TIER_KEYS}", cause=str(tier))

        conn = await self._connect()
        try:
            await self._require_local_owner(conn)

            cur = await conn.execute(
                "SELECT default_provider_policy, version FROM companies WHERE company_id = ?",
                (company_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(ORG_VALIDATION, "公司不存在", cause=company_id)

            current_version = row["version"]
            if current_version != expected_company_version:
                raise AcosError(SYS_OPTIMISTIC_LOCK_CONFLICT, "company_version 不匹配")

            mapping = self._normalize_tier_mapping(row["default_provider_policy"])

            if provider_id is None and model is None:
                mapping[tier] = None
            else:
                if not provider_id or not model:
                    raise AcosError(ORG_VALIDATION, "provider_id 与 model 必须成对提供或同时为空")
                await self._validate_tier_ref(conn, company_id, provider_id, model)
                mapping[tier] = {"provider_id": provider_id, "model": model}

            new_policy = json.dumps({k: mapping[k] for k in _TIER_KEYS})
            cur2 = await conn.execute(
                """UPDATE companies SET default_provider_policy = ?, version = version + 1,
                       updated_at = ?
                   WHERE company_id = ? AND version = ?""",
                (new_policy, _now_utc(), company_id, expected_company_version),
            )
            if cur2.rowcount != 1:
                raise AcosError(SYS_OPTIMISTIC_LOCK_CONFLICT, "并发更新冲突")
            await conn.commit()
            return {"company_version": current_version + 1,
                    "tier_mapping": {k: mapping[k] for k in _TIER_KEYS}}
        finally:
            await conn.close()

    def _normalize_tier_mapping(self, raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {k: data.get(k) for k in _TIER_KEYS}

    async def _validate_tier_ref(
        self, conn: aiosqlite.Connection, company_id: str, provider_id: str, model: str
    ) -> None:
        """引用必须是全局内置模型或当前公司私有模型。"""
        cur = await conn.execute(
            """SELECT 1 FROM provider_models
               WHERE provider_id = ? AND model = ?
                 AND (owner_company_id IS NULL OR owner_company_id = ?)""",
            (provider_id, model, company_id),
        )
        if await cur.fetchone() is None:
            raise AcosError(ORG_VALIDATION, "tier 引用的模型不存在或跨公司",
                            cause=f"{provider_id}/{model}")

    async def _get_tier_mapping(self, conn: aiosqlite.Connection, company_id: str) -> dict[str, Any]:
        cur = await conn.execute(
            "SELECT default_provider_policy FROM companies WHERE company_id = ?", (company_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return {k: None for k in _TIER_KEYS}
        return self._normalize_tier_mapping(row["default_provider_policy"])

    # ── provider.probe ───────────────────────────────────

    async def _probe(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        provider_id = params.get("provider_id")
        if not company_id or not provider_id:
            raise AcosError(PROV_VALIDATION, "缺少 company_id/provider_id")
        status = await self._registry.probe(company_id, provider_id)
        return {
            "provider_id": provider_id,
            "available": status.available,
            "healthy": status.healthy,
            "reason": status.reason,
        }

    # ── provider.credential.* ────────────────────────────

    async def _credential_set(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        provider_id = params.get("provider_id")
        credential_slot = params.get("credential_slot", "default")
        credential = params.get("credential")
        conn = await self._connect()
        try:
            await self._require_local_owner(conn)
        finally:
            await conn.close()
        return await self._broker.set_credential(company_id, provider_id, credential_slot, credential)

    async def _credential_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        provider_id = params.get("provider_id")
        credential_slot = params.get("credential_slot", "default")
        secret = await self._broker.get_credential(company_id, provider_id, credential_slot)
        return {"credential": secret}

    async def _credential_revoke(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        provider_id = params.get("provider_id")
        credential_slot = params.get("credential_slot", "default")
        conn = await self._connect()
        try:
            await self._require_local_owner(conn)
        finally:
            await conn.close()
        return await self._broker.revoke_credential(company_id, provider_id, credential_slot)

    # ── provider.runtime.* ───────────────────────────────

    async def _runtime_start(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        model = params.get("model", "fake-model-1")
        if not company_id:
            raise AcosError(PROV_VALIDATION, "缺少 company_id")
        return await self._runtime.start(
            adapter=self._fake,
            company_id=company_id,
            provider_id="fake",
            model=model,
            department_id=params.get("department_id", ""),
            employee_id=params.get("employee_id", ""),
        )

    async def _runtime_send(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = params.get("session_id")
        message = params.get("message", "")
        if not session_id:
            raise AcosError(PROV_VALIDATION, "缺少 session_id")
        run = await self._runtime.send(
            adapter=self._fake,
            session_id=session_id,
            message=message,
            task_id=params.get("task_id", ""),
            conversation_id=params.get("conversation_id", ""),
            trace_id=params.get("trace_id", ""),
            pricing_version_id=params.get("pricing_version_id"),
        )
        return {
            "run_id": run.run_id,
            "status": run.status,
            "events": [
                {"event_type": e.event_type, "payload": e.payload, "run_id": e.run_id}
                for e in run.events
            ],
        }

    async def _runtime_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = params.get("run_id")
        if not run_id:
            raise AcosError(PROV_VALIDATION, "缺少 run_id")
        ok = await self._runtime.cancel(self._fake, run_id)
        return {"ok": ok, "run_id": run_id}

    # ── helpers ──────────────────────────────────────────

    async def _ensure_manifest(self) -> None:
        conn = await self._connect()
        try:
            cur = await conn.execute("SELECT COUNT(*) FROM providers")
            count = (await cur.fetchone())[0]
        finally:
            await conn.close()
        if count == 0:
            await self._registry.import_manifest(load_manifest())
