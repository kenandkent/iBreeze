"""Provider 命名空间 RPC 方法集合（精简后仅保留 5 个核心方法）。"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from acos.providers.fake import FakeProviderAdapter
from acos.providers.registry import ProviderRegistry, load_manifest
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer
from acos.runtime.adapter import AgentRuntime

PROV_VALIDATION = "PROV-VALIDATION"


def _now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class ProviderMethods:
    """provider.* RPC 方法（仅 5 个核心方法）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._registry = ProviderRegistry(db_path)
        self._runtime = AgentRuntime(db_path)
        self._fake = FakeProviderAdapter()
        self._registry.register_driver("fake", self._fake)

    def register_to(self, server: RPCServer) -> None:
        server.register_method("provider.list", self._provider_list)
        server.register_method("provider.model.list", self._model_list)
        server.register_method("provider.runtime.start", self._runtime_start)
        server.register_method("provider.runtime.send", self._runtime_send)
        server.register_method("provider.runtime.cancel", self._runtime_cancel)

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    async def _ensure_manifest(self) -> None:
        conn = await self._connect()
        try:
            cur = await conn.execute("SELECT COUNT(*) FROM providers")
            count = (await cur.fetchone())[0]
        finally:
            await conn.close()
        if count == 0:
            await self._registry.import_manifest(load_manifest())

    async def _get_tier_mapping(self, conn: aiosqlite.Connection, company_id: str) -> dict[str, Any]:
        cur = await conn.execute(
            "SELECT default_provider_policy FROM companies WHERE company_id = ?", (company_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return {k: None for k in ("free", "standard", "premium")}
        try:
            data = json.loads(row["default_provider_policy"]) if row["default_provider_policy"] else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {k: data.get(k) for k in ("free", "standard", "premium")}

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

    async def _model_list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(PROV_VALIDATION, "缺少 company_id")
        provider_id = params.get("provider_id")

        await self._ensure_manifest()

        conn = await self._connect()
        try:
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
