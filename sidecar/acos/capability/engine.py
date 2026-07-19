"""Capability Engine - 装配运行配置。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from acos.capability.context_builder import ContextBuilder
from acos.capability.models import compute_checksum


@dataclass
class ResolvedRunConfig:
    """装配结果。"""
    employee_id: str = ""
    capability_id: str = ""
    capability_version: int = 0
    snapshot_checksum: str = ""
    system_prompt: str = ""
    tool_set: list[dict] = field(default_factory=list)
    knowledge_scope: dict = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    context_sections: list[dict] = field(default_factory=list)
    workspace: dict = field(default_factory=dict)
    security_policy: dict = field(default_factory=dict)
    review_spec: dict = field(default_factory=dict)
    decision_limits: dict = field(default_factory=dict)
    backend_requirements: list[str] = field(default_factory=list)
    config_hash: str = ""


class CapabilityEngine:
    """装配运行配置。"""

    DEFAULT_MODEL = {"provider": "default", "model": "default", "tier": "standard"}

    DEFAULT_REVIEW_SPEC = {
        "enabled": False,
        "reviewers": [],
        "auto_approve_threshold": 0,
    }

    DEFAULT_DECISION_LIMITS = {
        "max_cost_per_run": 0,
        "max_tokens": 0,
        "max_tool_calls": 0,
    }

    DEFAULT_SECURITY_POLICY = {
        "allow_network": True,
        "allow_file_write": False,
        "sandbox_enabled": True,
    }

    async def resolve(
        self,
        employee: dict,
        task_context: dict,
        capability_snapshot: dict,
        authorized_scope: dict,
    ) -> ResolvedRunConfig:
        """装配运行配置。"""
        from acos.rpc.errors import create_error

        snapshot_checksum = capability_snapshot.get("snapshot_checksum", "")
        expected = self._compute_snapshot_checksum(capability_snapshot)
        if snapshot_checksum and expected != snapshot_checksum:
            raise create_error(
                "CAP-SNAPSHOT-CHECKSUM-MISMATCH",
                "快照校验和不匹配",
                cause=f"expected {expected}, got {snapshot_checksum}",
            )

        employee_id = employee.get("employee_id", "")
        capability_id = capability_snapshot.get("capability_id", "")
        capability_version = capability_snapshot.get("version", 0)

        system_prompt = self._build_system_prompt(capability_snapshot)
        tool_set = self._resolve_tool_set(capability_snapshot, authorized_scope)
        knowledge_scope = self._resolve_knowledge_scope(capability_snapshot, authorized_scope)
        model = self._resolve_model(capability_snapshot, authorized_scope)
        review_spec = self._resolve_review_spec(capability_snapshot, authorized_scope)
        decision_limits = self._resolve_decision_limits(capability_snapshot, authorized_scope)
        security_policy = self._resolve_security_policy(capability_snapshot, authorized_scope)
        backend_requirements = self._resolve_backend_requirements(capability_snapshot, authorized_scope)

        context_builder = ContextBuilder()
        context_sections_raw = context_builder.build(
            employee, task_context, capability_snapshot, []
        )
        context_sections = [
            {"name": s.name, "content": s.content, "order": s.order}
            for s in context_sections_raw
        ]

        workspace = {
            "workspace_root": authorized_scope.get("workspace_root", ""),
            "workspace_types": authorized_scope.get("workspace_types", []),
        }

        config = ResolvedRunConfig(
            employee_id=employee_id,
            capability_id=capability_id,
            capability_version=capability_version,
            snapshot_checksum=snapshot_checksum or expected,
            system_prompt=system_prompt,
            tool_set=tool_set,
            knowledge_scope=knowledge_scope,
            model=model,
            context_sections=context_sections,
            workspace=workspace,
            security_policy=security_policy,
            review_spec=review_spec,
            decision_limits=decision_limits,
            backend_requirements=backend_requirements,
        )

        config.config_hash = self._compute_config_hash(config)
        return config

    def _compute_snapshot_checksum(self, snapshot: dict) -> str:
        data = {
            "capability_id": snapshot.get("capability_id", ""),
            "version": snapshot.get("version", 0),
            "dependencies": snapshot.get("dependencies", []),
        }
        return compute_checksum(data)

    def _build_system_prompt(self, snapshot: dict) -> str:
        segments = snapshot.get("prompt_segments", {})
        parts = []
        for key in ("system", "persona", "constraints"):
            if key in segments:
                parts.append(segments[key])
        return "\n\n".join(parts) if parts else snapshot.get("system_prompt", "")

    def _resolve_tool_set(self, snapshot: dict, scope: dict) -> list[dict]:
        allowed = scope.get("allowed_tools", [])
        snapshot_tools = snapshot.get("tools", [])
        if allowed:
            return [t for t in snapshot_tools if t.get("name") in allowed]
        return snapshot_tools

    def _resolve_knowledge_scope(self, snapshot: dict, scope: dict) -> dict:
        base = snapshot.get("knowledge_scope", {})

        # 向后兼容：扁平 ACL（allowed_knowledge_ids）直接过滤 refs
        allowed_ids = scope.get("allowed_knowledge_ids")
        if allowed_ids is not None and "refs" in base:
            filtered_refs = [
                ref for ref in base.get("refs", [])
                if ref.get("knowledge_id") in allowed_ids
            ]
            return {**base, "refs": filtered_refs}

        # P5-T2：按 AuthorizedScope 四分支逐分支求交（只收窄，不扩大）
        visibility_scope = base.get("visibility_scope", {})
        source_categories = base.get("source_categories", [])

        # capability 意图：只在声明为 true 的分支上可见
        want_company = bool(visibility_scope.get("company"))
        want_department = bool(visibility_scope.get("department"))
        want_task = bool(visibility_scope.get("task"))
        want_employee = bool(visibility_scope.get("employee"))

        # ACL 资格（来自 AuthorizedScope）
        acl_company = True  # 同公司在职职员恒可读 company 级
        acl_department = list(scope.get("visible_department_ids", []) or [])
        acl_task = list(scope.get("visible_task_ids", []) or [])
        own_id = scope.get("own_employee_id")
        private_ids = list(scope.get("private_visible_employee_ids", []) or [])
        acl_employee = sorted({x for x in [own_id, *private_ids] if x})

        # 逐分支求交：capability 未声明的分支直接为空（能力主动收窄）
        eff_company = acl_company and want_company
        eff_department = sorted(set(acl_department)) if want_department else []
        eff_task = sorted(set(acl_task)) if want_task else []
        eff_employee = sorted(set(acl_employee)) if want_employee else []

        return {
            "visibility_scope": {
                "company": want_company,
                "department": want_department,
                "task": want_task,
                "employee": want_employee,
            },
            "source_categories": list(source_categories),
            "acl": {
                "company": eff_company,
                "department": eff_department,
                "task": eff_task,
                "employee": eff_employee,
            },
        }

    def _resolve_model(self, snapshot: dict, scope: dict) -> dict:
        model_spec = snapshot.get("model", {})
        if not model_spec:
            model_spec = self.DEFAULT_MODEL.copy()
        tier_override = scope.get("model_tier_override")
        if tier_override:
            model_spec = {**model_spec, "tier": tier_override}
        return model_spec

    def _resolve_review_spec(self, snapshot: dict, scope: dict) -> dict:
        spec = snapshot.get("review_spec", self.DEFAULT_REVIEW_SPEC.copy())
        if scope.get("force_review"):
            spec = {**spec, "enabled": True}
        return spec

    def _resolve_decision_limits(self, snapshot: dict, scope: dict) -> dict:
        limits = snapshot.get("decision_limits", self.DEFAULT_DECISION_LIMITS.copy())
        scope_limits = scope.get("decision_limits", {})
        if scope_limits:
            merged = self.DEFAULT_DECISION_LIMITS.copy()
            merged.update(limits)
            merged.update(scope_limits)
            return merged
        return limits

    def _resolve_security_policy(self, snapshot: dict, scope: dict) -> dict:
        policy = snapshot.get("security_policy", self.DEFAULT_SECURITY_POLICY.copy())
        restrictions = scope.get("security_restrictions", {})
        if restrictions:
            merged = self.DEFAULT_SECURITY_POLICY.copy()
            merged.update(policy)
            for key, val in restrictions.items():
                if key in merged:
                    if isinstance(merged[key], bool):
                        merged[key] = merged[key] and val
                    else:
                        merged[key] = val
            return merged
        return policy

    def _resolve_backend_requirements(self, snapshot: dict, scope: dict) -> list[str]:
        base = snapshot.get("backend_requirements", [])
        scope_reqs = scope.get("backend_requirements", [])
        return list(set(base) | set(scope_reqs))

    def _compute_config_hash(self, config: ResolvedRunConfig) -> str:
        data = {
            "employee_id": config.employee_id,
            "capability_id": config.capability_id,
            "capability_version": config.capability_version,
            "snapshot_checksum": config.snapshot_checksum,
            "system_prompt": config.system_prompt,
            "tool_set": config.tool_set,
            "knowledge_scope": config.knowledge_scope,
            "model": config.model,
            "workspace": config.workspace,
            "security_policy": config.security_policy,
            "review_spec": config.review_spec,
            "decision_limits": config.decision_limits,
            "backend_requirements": config.backend_requirements,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
