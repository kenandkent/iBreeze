"""Settings RPC 方法集合。

注册 settings.company.* / settings.knowledgePolicy.* / settings.securityPolicy.*
/ settings.workspacePolicy.* / settings.notification.*。

公司隔离：所有查询按 company_id 过滤。版本化策略采用乐观锁 CAS，
并发冲突返回 SYS-OPTIMISTIC-LOCK-CONFLICT；knowledgePolicy 云端模式需
当前版本显式同意，否则 KG-CLOUD-CONSENT-REQUIRED。
"""

from __future__ import annotations

import json
from typing import Any

from acos.rpc.errors import AcosError, create_error
from acos.settings.service import SettingsService
from acos.rpc.server import RPCServer


class SettingsMethods:
    """设置相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._service = SettingsService(db_path)

    def register_to(self, server: RPCServer) -> None:
        # company
        server.register_method("settings.company.get", self._company_get)
        server.register_method("settings.company.update", self._company_update)
        # knowledge policy
        server.register_method("settings.knowledgePolicy.get", self._knowledge_get)
        server.register_method("settings.knowledgePolicy.update", self._knowledge_update)
        # security policy
        server.register_method("settings.securityPolicy.get", self._security_get)
        server.register_method("settings.securityPolicy.update", self._security_update)
        # workspace policy
        server.register_method("settings.workspacePolicy.get", self._workspace_get)
        server.register_method("settings.workspacePolicy.update", self._workspace_update)
        # notification policy
        server.register_method("settings.notification.get", self._notification_get)
        server.register_method("settings.notification.update", self._notification_update)

    # ── company ───────────────────────────────────────────────

    async def _company_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        company = await self._service.get_company(company_id)
        if company is None:
            raise create_error("ORG-NOT-FOUND", "公司不存在")
        return {
            "company_id": company["company_id"],
            "name": company["name"],
            "status": company["status"],
            "version": company["version"],
            "default_provider_policy": json.loads(company["default_provider_policy"]),
            "default_budget_policy": json.loads(company["default_budget_policy"]),
        }

    async def _company_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        expected_version = params.get("expected_version", 1)
        updates = {k: v for k, v in params.items() if k in ("name",)}
        try:
            result = await self._service.update_company(
                company_id, expected_version, updates
            )
        except AcosError:
            raise
        return result

    # ── knowledge policy ──────────────────────────────────────

    async def _knowledge_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        policy = await self._service.get_policy("knowledge", company_id)
        if policy is None:
            raise create_error("SYS-INTERNAL", "未找到 knowledge 策略")
        return {
            "company_id": company_id,
            "policy_id": policy["policy_id"],
            "version": policy["version"],
            "config": policy["config"],
        }

    async def _knowledge_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        expected_version = params.get("expected_policy_version")
        if expected_version is None:
            raise create_error("ORG-VALIDATION", "缺少 expected_policy_version")
        config = params.get("config")
        if not isinstance(config, dict):
            raise create_error("ORG-VALIDATION", "缺少 config")
        result = await self._service.update_policy(
            "knowledge", company_id, expected_version, config, consent_required=True
        )
        return {
            "company_id": result["company_id"],
            "policy_id": result["policy_id"],
            "version": result["version"],
            "config": result["config"],
        }

    # ── security policy ───────────────────────────────────────

    async def _security_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        policy = await self._service.get_policy("security", company_id)
        if policy is None:
            raise create_error("SYS-INTERNAL", "未找到 security 策略")
        return {
            "company_id": company_id,
            "policy_id": policy["policy_id"],
            "version": policy["version"],
            "config": policy["config"],
        }

    async def _security_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        expected_version = params.get("expected_policy_version")
        if expected_version is None:
            raise create_error("ORG-VALIDATION", "缺少 expected_policy_version")
        config = params.get("config")
        if not isinstance(config, dict):
            raise create_error("ORG-VALIDATION", "缺少 config")
        result = await self._service.update_policy(
            "security", company_id, expected_version, config
        )
        return {
            "company_id": result["company_id"],
            "policy_id": result["policy_id"],
            "version": result["version"],
            "config": result["config"],
        }

    # ── workspace policy ──────────────────────────────────────

    async def _workspace_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        policy = await self._service.get_policy("workspace", company_id)
        if policy is None:
            raise create_error("SYS-INTERNAL", "未找到 workspace 策略")
        return {
            "company_id": company_id,
            "policy_id": policy["policy_id"],
            "version": policy["version"],
            "config": policy["config"],
        }

    async def _workspace_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        expected_version = params.get("expected_policy_version")
        if expected_version is None:
            raise create_error("ORG-VALIDATION", "缺少 expected_policy_version")
        config = params.get("config")
        if not isinstance(config, dict):
            raise create_error("ORG-VALIDATION", "缺少 config")
        result = await self._service.update_policy(
            "workspace", company_id, expected_version, config
        )
        return {
            "company_id": result["company_id"],
            "policy_id": result["policy_id"],
            "version": result["version"],
            "config": result["config"],
        }

    # ── notification policy ───────────────────────────────────

    async def _notification_get(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        policy = await self._service.get_policy("notification", company_id)
        if policy is None:
            raise create_error("SYS-INTERNAL", "未找到 notification 策略")
        return {
            "company_id": company_id,
            "policy_id": policy["policy_id"],
            "version": policy["version"],
            "config": policy["config"],
        }

    async def _notification_update(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error("ORG-VALIDATION", "缺少 company_id")
        expected_version = params.get("expected_policy_version")
        if expected_version is None:
            raise create_error("ORG-VALIDATION", "缺少 expected_policy_version")
        config = params.get("config")
        if not isinstance(config, dict):
            raise create_error("ORG-VALIDATION", "缺少 config")
        result = await self._service.update_policy(
            "notification", company_id, expected_version, config
        )
        return {
            "company_id": result["company_id"],
            "policy_id": result["policy_id"],
            "version": result["version"],
            "config": result["config"],
        }
