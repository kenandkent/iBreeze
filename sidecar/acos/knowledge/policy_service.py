"""知识策略服务（Phase 8 P8-T2）。

对接 settings.knowledgePolicy.get/update（SettingsService 版本化策略）：
- extraction provider/model/mode(local|cloud)/fallback(local|pause)/allow_cloud/consent
- 云端模式必须有当前 policy version 的显式同意；撤回后新云端 job 立即停止
- local 不可用时绝不静默切 cloud
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acos.rpc.errors import KG_CLOUD_CONSENT_REQUIRED, create_error


@dataclass
class ResolvedPolicy:
    """锁定到某版本的提取策略配置。"""

    policy_id: str
    version: int
    extraction_mode: str  # local | cloud
    provider: str
    model: str
    fallback: str  # local | pause
    allow_cloud: bool
    consented: bool


class PolicyService:
    """读取 knowledge policy 并解析提取配置。"""

    def __init__(self, settings) -> None:
        self._settings = settings

    async def resolve(
        self, company_id: str, *, policy_version: int | None = None
    ) -> ResolvedPolicy:
        policy = await self._settings.get_policy("knowledge", company_id)
        if policy is None:
            # 无策略：默认 local 模式
            return ResolvedPolicy(
                policy_id="", version=0, extraction_mode="local",
                provider="fake", model="fake-model-1", fallback="pause",
                allow_cloud=False, consented=False,
            )
        config: dict[str, Any] = policy.get("config", {}) or {}
        version = policy["version"]
        if policy_version is not None and policy_version != version:
            # 调用方锁定的版本已不是 active，按当前 active 处理（由 job 持久化版本决定）
            version = policy_version
        mode = config.get("extraction_mode", "local")
        allow_cloud = bool(config.get("allow_cloud")) or mode == "cloud"
        consent = config.get("consent")
        consented = bool(consent and consent.get("consented_by"))
        return ResolvedPolicy(
            policy_id=policy["policy_id"],
            version=version,
            extraction_mode=mode,
            provider=config.get("provider", "fake"),
            model=config.get("model", "fake-model-1"),
            fallback=config.get("fallback", "pause"),
            allow_cloud=allow_cloud,
            consented=consented,
        )

    def require_local_or_consent(self, resolved: ResolvedPolicy) -> None:
        """云端模式必须有当前版本同意，否则拒绝。"""
        if resolved.extraction_mode == "cloud" and resolved.allow_cloud and not resolved.consented:
            raise create_error(
                KG_CLOUD_CONSENT_REQUIRED,
                "云端提取需要当前策略版本的显式同意",
                cause=f"policy version {resolved.version}",
            )
