"""Capability RPC 方法集合（精简后仅保留 2 个）。"""

from __future__ import annotations

from typing import Any

from acos.capability.engine import CapabilityEngine
from acos.capability.snapshot import CapabilitySnapshot
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer


class CapabilityMethods:
    """能力相关的 RPC 方法（仅 cap.snapshot.build / cap.engine.resolve）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._snapshot_svc = CapabilitySnapshot()
        self._engine = CapabilityEngine()

    def register_to(self, server: RPCServer) -> None:
        server.register_method("cap.snapshot.build", self._snapshot_build)
        server.register_method("cap.engine.resolve", self._engine_resolve)

    async def _snapshot_build(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        import aiosqlite

        try:
            async with aiosqlite.connect(self._db_path) as db:
                lock = await self._snapshot_svc.build_snapshot(db, cap_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {
            "snapshot_id": lock.snapshot_id,
            "capability_id": lock.capability_id,
            "capability_version": lock.capability_version,
            "snapshot_checksum": lock.snapshot_checksum,
            "dependency_tree": lock.dependency_tree,
        }

    async def _engine_resolve(self, params: dict[str, Any]) -> dict[str, Any]:
        employee = params.get("employee")
        task_context = params.get("task_context", {})
        capability_snapshot = params.get("capability_snapshot")
        authorized_scope = params.get("authorized_scope", {})
        if not employee or not capability_snapshot:
            raise AcosError(
                code="CAP-VALIDATION",
                message="缺少 employee 或 capability_snapshot",
            )
        try:
            config = await self._engine.resolve(
                employee, task_context, capability_snapshot, authorized_scope
            )
        except AcosError:
            raise
        return {
            "employee_id": config.employee_id,
            "capability_id": config.capability_id,
            "capability_version": config.capability_version,
            "snapshot_checksum": config.snapshot_checksum,
            "system_prompt": config.system_prompt,
            "tool_set": config.tool_set,
            "knowledge_scope": config.knowledge_scope,
            "model": config.model,
            "context_sections": config.context_sections,
            "workspace": config.workspace,
            "security_policy": config.security_policy,
            "review_spec": config.review_spec,
            "decision_limits": config.decision_limits,
            "backend_requirements": config.backend_requirements,
            "config_hash": config.config_hash,
        }
