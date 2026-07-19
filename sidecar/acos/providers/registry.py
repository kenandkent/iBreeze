"""ProviderRegistry：全局 Driver 注册表 + 内置 manifest 幂等导入 + 公司级可用性探测。

对照设计方案 §6.11：
- providers 是随应用发布的全局 Driver 注册表。
- 内置 Driver 随包提供带 manifest_version/hash 的只读 provider-models.json，
  按 (provider_id, model) WHERE owner_company_id IS NULL 幂等 upsert 静态能力。
- probe 只更新公司级 (company_id, provider_id) 的 Availability，不改写静态能力。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from acos.providers.base import AvailabilityStatus, ProviderAdapter
from acos.rpc.errors import AcosError

PROV_MANIFEST_INVALID = "PROV-MANIFEST-INVALID"

_MANIFEST_PATH = Path(__file__).resolve().parent / "provider-models.json"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ManifestModel:
    provider_id: str
    model: str
    display_name: str
    tier: str
    billing_mode: str
    enforces_output_cap: bool
    context_window: int
    supports: list[str]
    latency_hint: str


@dataclass
class LoadedManifest:
    manifest_version: str
    manifest_hash: str
    providers: list[dict[str, Any]] = field(default_factory=list)


def load_manifest(path: Path | None = None) -> LoadedManifest:
    """加载并校验内置 manifest，计算 SHA-256 hash。"""
    p = path or _MANIFEST_PATH
    raw = p.read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw)

    version = data.get("manifest_version")
    if not version:
        raise AcosError(PROV_MANIFEST_INVALID, "manifest 缺少 manifest_version")

    providers = data.get("providers", [])
    if not isinstance(providers, list) or not providers:
        raise AcosError(PROV_MANIFEST_INVALID, "manifest providers 非法")

    # v1 约束：至少一个 OpenAI chat 模型，model 必须是具体 ID（禁止 latest/档位别名）
    _validate_v1_constraints(providers)

    return LoadedManifest(
        manifest_version=str(version),
        manifest_hash=manifest_hash,
        providers=providers,
    )


_FORBIDDEN_MODEL_TOKENS = {"latest", "free", "standard", "premium"}


def _validate_v1_constraints(providers: list[dict[str, Any]]) -> None:
    has_openai_chat = False
    for prov in providers:
        pid = prov.get("provider_id")
        if not pid:
            raise AcosError(PROV_MANIFEST_INVALID, "provider 缺少 provider_id")
        for m in prov.get("models", []):
            model = m.get("model", "")
            if not model:
                raise AcosError(PROV_MANIFEST_INVALID, "模型缺少具体 ID")
            lowered = model.lower()
            if lowered in _FORBIDDEN_MODEL_TOKENS or lowered.endswith("-latest") or lowered == "latest":
                raise AcosError(
                    PROV_MANIFEST_INVALID,
                    "禁止 latest/档位名/漂移别名作为 model ID",
                    cause=model,
                )
            if pid == "openai":
                has_openai_chat = True
    if not has_openai_chat:
        raise AcosError(PROV_MANIFEST_INVALID, "v1 manifest 必须至少登记一个 OpenAI chat 模型")


class ProviderRegistry:
    """全局 Driver 注册表（进程内） + 数据库静态能力/可用性持久化。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._drivers: dict[str, ProviderAdapter] = {}

    def register_driver(self, provider_id: str, adapter: ProviderAdapter) -> None:
        """注册内置/自定义 Driver 到进程内注册表。"""
        self._drivers[provider_id] = adapter

    def get_driver(self, provider_id: str) -> ProviderAdapter | None:
        return self._drivers.get(provider_id)

    async def import_manifest(self, manifest: LoadedManifest | None = None) -> dict[str, Any]:
        """按 (provider_id, model) WHERE owner_company_id IS NULL 幂等 upsert 内置静态能力。

        同时 upsert providers 全局 Driver 行。返回导入统计。
        """
        m = manifest or load_manifest()
        inserted = 0
        updated = 0
        conn = await aiosqlite.connect(self._db_path)
        try:
            for prov in m.providers:
                pid = prov["provider_id"]
                await conn.execute(
                    """INSERT INTO providers (provider_id, name, provider_type, status, config)
                       VALUES (?, ?, ?, 'active', '{}')
                       ON CONFLICT(provider_id) DO UPDATE SET
                           name = excluded.name,
                           provider_type = excluded.provider_type""",
                    (pid, prov.get("name", pid), prov.get("provider_type", "api")),
                )
                for md in prov.get("models", []):
                    model = md["model"]
                    cur = await conn.execute(
                        """SELECT model_id FROM provider_models
                           WHERE provider_id = ? AND model = ? AND owner_company_id IS NULL""",
                        (pid, model),
                    )
                    existing = await cur.fetchone()
                    supports = json.dumps(md.get("supports", []))
                    if existing is None:
                        await conn.execute(
                            """INSERT INTO provider_models
                               (model_id, provider_id, model, display_name, supports,
                                owner_company_id, source, manifest_version, config_version,
                                tier, billing_mode, enforces_output_cap, context_window, latency_hint)
                               VALUES (?, ?, ?, ?, ?, NULL, 'builtin_manifest', ?, 1,
                                       ?, ?, ?, ?, ?)""",
                            (
                                f"pm-{uuid.uuid4().hex}", pid, model,
                                md.get("display_name", model), supports,
                                m.manifest_version,
                                md.get("tier", "standard"),
                                md.get("billing_mode", "unknown"),
                                1 if md.get("enforces_output_cap") else 0,
                                int(md.get("context_window", 0)),
                                md.get("latency_hint", ""),
                            ),
                        )
                        inserted += 1
                    else:
                        await conn.execute(
                            """UPDATE provider_models SET
                                   display_name = ?, supports = ?, manifest_version = ?,
                                   tier = ?, billing_mode = ?, enforces_output_cap = ?,
                                   context_window = ?, latency_hint = ?
                               WHERE model_id = ?""",
                            (
                                md.get("display_name", model), supports, m.manifest_version,
                                md.get("tier", "standard"),
                                md.get("billing_mode", "unknown"),
                                1 if md.get("enforces_output_cap") else 0,
                                int(md.get("context_window", 0)),
                                md.get("latency_hint", ""),
                                existing[0],
                            ),
                        )
                        updated += 1
            await conn.commit()
        finally:
            await conn.close()
        return {
            "manifest_version": m.manifest_version,
            "manifest_hash": m.manifest_hash,
            "inserted": inserted,
            "updated": updated,
        }

    async def probe(self, company_id: str, provider_id: str) -> AvailabilityStatus:
        """探测公司级 Provider 可用性，只更新 Availability 投影，不改静态能力。"""
        if not company_id or not provider_id:
            raise AcosError("PROV-VALIDATION", "probe 参数不完整")

        driver = self._drivers.get(provider_id)
        if driver is None:
            status = AvailabilityStatus(available=False, reason="driver_not_registered", healthy=False)
        else:
            status = await driver.check_availability()

        conn = await aiosqlite.connect(self._db_path)
        try:
            cur = await conn.execute(
                "SELECT version FROM provider_availability WHERE company_id = ? AND provider_id = ?",
                (company_id, provider_id),
            )
            row = await cur.fetchone()
            now = _now_utc()
            if row is None:
                await conn.execute(
                    """INSERT INTO provider_availability
                       (company_id, provider_id, available, healthy, reason, probed_at, version)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    (company_id, provider_id, 1 if status.available else 0,
                     1 if status.healthy else 0, status.reason, now),
                )
            else:
                await conn.execute(
                    """UPDATE provider_availability SET
                           available = ?, healthy = ?, reason = ?, probed_at = ?, version = version + 1
                       WHERE company_id = ? AND provider_id = ?""",
                    (1 if status.available else 0, 1 if status.healthy else 0,
                     status.reason, now, company_id, provider_id),
                )
            await conn.commit()
        finally:
            await conn.close()
        return status

    async def get_availability(self, company_id: str, provider_id: str) -> dict[str, Any] | None:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                "SELECT * FROM provider_availability WHERE company_id = ? AND provider_id = ?",
                (company_id, provider_id),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
        finally:
            await conn.close()
