"""Capability/Skill/PromptAsset/Template RPC 方法集合。"""

from __future__ import annotations

import json
from typing import Any

from acos.capability.engine import CapabilityEngine
from acos.capability.metrics import MetricsReader
from acos.capability.models import Capability, PromptAsset, Skill
from acos.capability.prompt_service import PromptAssetService
from acos.capability.service import CapabilityService
from acos.capability.skill_service import SkillService
from acos.capability.snapshot import CapabilitySnapshot
from acos.capability.versioning import VersioningService
from acos.organization.template_service import TemplateService
from acos.rpc.errors import AcosError
from acos.rpc.server import RPCServer


class CapabilityMethods:
    """能力相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._skill_svc = SkillService(db_path)
        self._prompt_svc = PromptAssetService(db_path)
        self._cap_svc = CapabilityService(db_path)
        self._template_svc = TemplateService(db_path)
        self._versioning_svc = VersioningService(db_path)
        self._snapshot_svc = CapabilitySnapshot()
        self._metrics_reader = MetricsReader(db_path)
        self._engine = CapabilityEngine()

    def register_to(self, server: RPCServer) -> None:
        # Skill
        server.register_method("cap.skill.list", self._skill_list)
        server.register_method("cap.skill.get", self._skill_get)
        server.register_method("cap.skill.create", self._skill_create)
        server.register_method("cap.skill.update", self._skill_update)
        server.register_method("cap.skill.saveDraft", self._skill_save_draft)
        server.register_method("cap.skill.version.list", self._skill_version_list)
        server.register_method("cap.skill.createVersion", self._skill_create_version)
        server.register_method("cap.skill.submitReview", self._skill_submit_review)
        server.register_method("cap.skill.publish", self._skill_publish)
        server.register_method("cap.skill.deprecate", self._skill_deprecate)
        server.register_method("cap.skill.archive", self._skill_archive)
        # PromptAsset
        server.register_method("cap.prompt.list", self._prompt_list)
        server.register_method("cap.prompt.get", self._prompt_get)
        server.register_method("cap.prompt.create", self._prompt_create)
        server.register_method("cap.prompt.update", self._prompt_update)
        server.register_method("cap.prompt.saveDraft", self._prompt_save_draft)
        server.register_method("cap.prompt.version.list", self._prompt_version_list)
        server.register_method("cap.prompt.createVersion", self._prompt_create_version)
        server.register_method("cap.prompt.submitReview", self._prompt_submit_review)
        server.register_method("cap.prompt.publish", self._prompt_publish)
        server.register_method("cap.prompt.deprecate", self._prompt_deprecate)
        server.register_method("cap.prompt.archive", self._prompt_archive)
        # Capability
        server.register_method("cap.capability.list", self._capability_list)
        server.register_method("cap.capability.get", self._capability_get)
        server.register_method("cap.capability.create", self._capability_create)
        server.register_method("cap.capability.update", self._capability_update)
        server.register_method("cap.capability.get_bindings", self._capability_get_bindings)
        server.register_method("cap.capability.version.list", self._capability_version_list)
        server.register_method("cap.capability.createVersion", self._capability_create_version)
        server.register_method("cap.capability.submitReview", self._capability_submit_review)
        server.register_method("cap.capability.publish", self._capability_publish)
        server.register_method("cap.capability.deprecate", self._capability_deprecate)
        server.register_method("cap.capability.archive", self._capability_archive)
        # Snapshot / Metrics
        server.register_method("cap.snapshot.build", self._snapshot_build)
        server.register_method("cap.metrics.get", self._metrics_get)
        # Capability Engine 主装配
        server.register_method("cap.engine.resolve", self._engine_resolve)
        # Template
        server.register_method("org.template.list", self._template_list)
        server.register_method("org.template.get", self._template_get)
        server.register_method("org.template.create", self._template_create)
        server.register_method("org.template.update", self._template_update)
        server.register_method("org.template.activate", self._template_activate)
        server.register_method("org.template.archive", self._template_archive)

    # ── Skill ──────────────────────────────────────────────

    async def _skill_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        status = params.get("status")
        skills = await self._skill_svc.list_by_company(company_id, status)
        return [
            {
                "skill_id": s.skill_id,
                "company_scope": s.company_scope,
                "company_id": s.company_id,
                "name": s.name,
                "prompt_asset_id": s.prompt_asset_id,
                "version": s.version,
                "status": s.status,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in skills
        ]

    async def _skill_get(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        if not skill_id:
            return {"error": "missing skill_id"}
        skill = await self._skill_svc.get(skill_id)
        if skill is None:
            return {"error": "not found"}
        return {
            "skill_id": skill.skill_id,
            "company_scope": skill.company_scope,
            "company_id": skill.company_id,
            "name": skill.name,
            "prompt_asset_id": skill.prompt_asset_id,
            "prompt_asset_version": skill.prompt_asset_version,
            "prompt_asset_checksum": skill.prompt_asset_checksum,
            "tool_bindings": skill.tool_bindings,
            "knowledge_refs": skill.knowledge_refs,
            "input_schema": skill.input_schema,
            "output_schema": skill.output_schema,
            "checksum": skill.checksum,
            "version": skill.version,
            "status": skill.status,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at,
        }

    async def _skill_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        company_scope = params.get("company_scope", "company")
        company_id = params.get("company_id")
        if not name:
            return {"error": "missing name"}

        skill = Skill(
            company_scope=company_scope,
            company_id=company_id,
            name=name,
            prompt_asset_id=params.get("prompt_asset_id", ""),
            prompt_asset_version=params.get("prompt_asset_version", 0),
            tool_bindings=params.get("tool_bindings", []),
            knowledge_refs=params.get("knowledge_refs", []),
            input_schema=params.get("input_schema", {}),
            output_schema=params.get("output_schema", {}),
        )
        skill = await self._skill_svc.create(skill)
        return {"skill_id": skill.skill_id, "version": skill.version, "status": skill.status}

    async def _skill_update(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        expected_version = params.get("expected_version")
        if not skill_id or expected_version is None:
            return {"error": "missing skill_id or expected_version"}

        skill = await self._skill_svc.get(skill_id)
        if skill is None:
            return {"error": "not found"}

        for field in ("name", "prompt_asset_id", "prompt_asset_version"):
            if field in params:
                setattr(skill, field, params[field])
        if "tool_bindings" in params:
            skill.tool_bindings = params["tool_bindings"]
        if "knowledge_refs" in params:
            skill.knowledge_refs = params["knowledge_refs"]
        if "input_schema" in params:
            skill.input_schema = params["input_schema"]
        if "output_schema" in params:
            skill.output_schema = params["output_schema"]

        skill = await self._skill_svc.save_draft(skill, expected_version)
        return {"skill_id": skill.skill_id, "version": skill.version, "status": skill.status}

    # ── PromptAsset ────────────────────────────────────────

    async def _prompt_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        status = params.get("status")
        assets = await self._prompt_svc.list_by_company(company_id, status)
        return [
            {
                "prompt_asset_id": a.prompt_asset_id,
                "company_scope": a.company_scope,
                "company_id": a.company_id,
                "name": a.name,
                "version": a.version,
                "status": a.status,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in assets
        ]

    async def _prompt_get(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        if not prompt_id:
            return {"error": "missing prompt_id"}
        asset = await self._prompt_svc.get(prompt_id)
        if asset is None:
            return {"error": "not found"}
        return {
            "prompt_asset_id": asset.prompt_asset_id,
            "company_scope": asset.company_scope,
            "company_id": asset.company_id,
            "name": asset.name,
            "segments": asset.segments,
            "variables": asset.variables,
            "context_slots": asset.context_slots,
            "checksum": asset.checksum,
            "version": asset.version,
            "status": asset.status,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }

    async def _prompt_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        company_scope = params.get("company_scope", "company")
        company_id = params.get("company_id")
        if not name:
            return {"error": "missing name"}

        asset = PromptAsset(
            company_scope=company_scope,
            company_id=company_id,
            name=name,
            segments=params.get("segments", {}),
            variables=params.get("variables", []),
            context_slots=params.get("context_slots", []),
        )
        asset = await self._prompt_svc.create(asset)
        return {"prompt_asset_id": asset.prompt_asset_id, "version": asset.version, "status": asset.status}

    async def _prompt_update(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        expected_version = params.get("expected_version")
        if not prompt_id or expected_version is None:
            return {"error": "missing prompt_id or expected_version"}

        asset = await self._prompt_svc.get(prompt_id)
        if asset is None:
            return {"error": "not found"}

        if "name" in params:
            asset.name = params["name"]
        if "segments" in params:
            asset.segments = params["segments"]
        if "variables" in params:
            asset.variables = params["variables"]
        if "context_slots" in params:
            asset.context_slots = params["context_slots"]

        asset = await self._prompt_svc.save_draft(asset, expected_version)
        return {"prompt_asset_id": asset.prompt_asset_id, "version": asset.version, "status": asset.status}

    # ── Capability ─────────────────────────────────────────

    async def _capability_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        status = params.get("status")
        caps = await self._cap_svc.list_by_company(company_id, status)
        return [
            {
                "capability_id": c.capability_id,
                "company_scope": c.company_scope,
                "company_id": c.company_id,
                "name": c.name,
                "description": c.description,
                "version": c.version,
                "status": c.status,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in caps
        ]

    async def _capability_get(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        if not cap_id:
            return {"error": "missing capability_id"}
        cap = await self._cap_svc.get(cap_id)
        if cap is None:
            return {"error": "not found"}
        bindings = await self._cap_svc.get_bindings(cap_id, cap.version)
        return {
            "capability_id": cap.capability_id,
            "company_scope": cap.company_scope,
            "company_id": cap.company_id,
            "name": cap.name,
            "description": cap.description,
            "source_category": cap.source_category,
            "visibility": cap.visibility,
            "cost_policy": cap.cost_policy,
            "checksum": cap.checksum,
            "version": cap.version,
            "status": cap.status,
            "created_at": cap.created_at,
            "updated_at": cap.updated_at,
            "skill_bindings": bindings,
        }

    async def _capability_create(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        company_scope = params.get("company_scope", "company")
        company_id = params.get("company_id")
        if not name:
            return {"error": "missing name"}

        cap = Capability(
            company_scope=company_scope,
            company_id=company_id,
            name=name,
            description=params.get("description", ""),
            source_category=params.get("source_category", "custom"),
            visibility=params.get("visibility", "company"),
            cost_policy=params.get("cost_policy", {"default_model_tier": "free", "stability_level": 5}),
        )
        bindings = params.get("skill_bindings", [])
        cap = await self._cap_svc.create(cap, bindings)
        return {"capability_id": cap.capability_id, "version": cap.version, "status": cap.status}

    async def _capability_update(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        expected_version = params.get("expected_version")
        if not cap_id or expected_version is None:
            return {"error": "missing capability_id or expected_version"}

        cap = await self._cap_svc.get(cap_id)
        if cap is None:
            return {"error": "not found"}

        for field in ("name", "description", "source_category", "visibility"):
            if field in params:
                setattr(cap, field, params[field])
        if "cost_policy" in params:
            cap.cost_policy = params["cost_policy"]

        bindings = params.get("skill_bindings")
        cap = await self._cap_svc.save_draft(cap, expected_version, bindings)
        return {"capability_id": cap.capability_id, "version": cap.version, "status": cap.status}

    async def _capability_get_bindings(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        return await self._cap_svc.get_bindings(cap_id, version)

    # ── Skill: 版本与发布状态机 ─────────────────────────────

    async def _skill_save_draft(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._skill_update(params)

    async def _skill_version_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        skill_id = params.get("skill_id")
        if not skill_id:
            return [{"error": "missing skill_id"}]
        versions = await self._skill_svc.list_versions(skill_id)
        return [
            {
                "skill_id": s.skill_id,
                "version": s.version,
                "status": s.status,
                "checksum": s.checksum,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in versions
        ]

    async def _skill_create_version(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        from_version = params.get("from_version", 1)
        if not skill_id:
            return {"error": "missing skill_id"}
        try:
            s = await self._skill_svc.create_version(skill_id, from_version)
        except ValueError as e:
            return {"error": str(e)}
        return {"skill_id": s.skill_id, "version": s.version, "status": s.status}

    async def _skill_submit_review(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        version = params.get("version", 1)
        if not skill_id:
            return {"error": "missing skill_id"}
        try:
            await self._versioning_svc.submit_review("skill", skill_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"skill_id": skill_id, "version": version, "status": "review"}

    async def _skill_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        version = params.get("version", 1)
        if not skill_id:
            return {"error": "missing skill_id"}
        try:
            await self._versioning_svc.publish("skill", skill_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"skill_id": skill_id, "version": version, "status": "published"}

    async def _skill_deprecate(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        version = params.get("version", 1)
        if not skill_id:
            return {"error": "missing skill_id"}
        try:
            await self._versioning_svc.deprecate("skill", skill_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"skill_id": skill_id, "version": version, "status": "deprecated"}

    async def _skill_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        skill_id = params.get("skill_id")
        version = params.get("version", 1)
        if not skill_id:
            return {"error": "missing skill_id"}
        try:
            await self._versioning_svc.archive("skill", skill_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"skill_id": skill_id, "version": version, "status": "archived"}

    # ── PromptAsset: 版本与发布状态机 ──────────────────────

    async def _prompt_save_draft(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._prompt_update(params)

    async def _prompt_version_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        if not prompt_id:
            return [{"error": "missing prompt_id"}]
        versions = await self._prompt_svc.list_versions(prompt_id)
        return [
            {
                "prompt_asset_id": a.prompt_asset_id,
                "version": a.version,
                "status": a.status,
                "checksum": a.checksum,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in versions
        ]

    async def _prompt_create_version(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        from_version = params.get("from_version", 1)
        if not prompt_id:
            return {"error": "missing prompt_id"}
        try:
            a = await self._prompt_svc.create_version(prompt_id, from_version)
        except ValueError as e:
            return {"error": str(e)}
        return {"prompt_asset_id": a.prompt_asset_id, "version": a.version, "status": a.status}

    async def _prompt_submit_review(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        version = params.get("version", 1)
        if not prompt_id:
            return {"error": "missing prompt_id"}
        try:
            await self._versioning_svc.submit_review("prompt_asset", prompt_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"prompt_asset_id": prompt_id, "version": version, "status": "review"}

    async def _prompt_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        version = params.get("version", 1)
        if not prompt_id:
            return {"error": "missing prompt_id"}
        try:
            await self._versioning_svc.publish("prompt_asset", prompt_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"prompt_asset_id": prompt_id, "version": version, "status": "published"}

    async def _prompt_deprecate(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        version = params.get("version", 1)
        if not prompt_id:
            return {"error": "missing prompt_id"}
        try:
            await self._versioning_svc.deprecate("prompt_asset", prompt_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"prompt_asset_id": prompt_id, "version": version, "status": "deprecated"}

    async def _prompt_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        prompt_id = params.get("prompt_id") or params.get("prompt_asset_id")
        version = params.get("version", 1)
        if not prompt_id:
            return {"error": "missing prompt_id"}
        try:
            await self._versioning_svc.archive("prompt_asset", prompt_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"prompt_asset_id": prompt_id, "version": version, "status": "archived"}

    # ── Capability: 版本与发布状态机 ───────────────────────

    async def _capability_version_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        cap_id = params.get("capability_id")
        if not cap_id:
            return [{"error": "missing capability_id"}]
        versions = await self._cap_svc.list_versions(cap_id)
        return [
            {
                "capability_id": c.capability_id,
                "version": c.version,
                "status": c.status,
                "checksum": c.checksum,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in versions
        ]

    async def _capability_create_version(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        from_version = params.get("from_version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        try:
            c = await self._cap_svc.create_version(cap_id, from_version)
        except ValueError as e:
            return {"error": str(e)}
        return {"capability_id": c.capability_id, "version": c.version, "status": c.status}

    async def _capability_submit_review(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        try:
            await self._versioning_svc.submit_review("capability", cap_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"capability_id": cap_id, "version": version, "status": "review"}

    async def _capability_publish(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        try:
            await self._versioning_svc.publish("capability", cap_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"capability_id": cap_id, "version": version, "status": "published"}

    async def _capability_deprecate(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        try:
            await self._versioning_svc.deprecate("capability", cap_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"capability_id": cap_id, "version": version, "status": "deprecated"}

    async def _capability_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        try:
            await self._versioning_svc.archive("capability", cap_id, version)
        except ValueError as e:
            return {"error": str(e)}
        return {"capability_id": cap_id, "version": version, "status": "archived"}

    # ── Snapshot / Metrics ─────────────────────────────────

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

    async def _metrics_get(self, params: dict[str, Any]) -> dict[str, Any]:
        cap_id = params.get("capability_id")
        version = params.get("version", 1)
        if not cap_id:
            return {"error": "missing capability_id"}
        m = await self._metrics_reader.get_metrics(cap_id, version)
        if m is None:
            return {"error": "not found"}
        return {
            "capability_id": m.capability_id,
            "capability_version": m.capability_version,
            "success_rate": m.success_rate,
            "avg_cost": m.avg_cost,
            "review_pass_rate": m.review_pass_rate,
            "avg_downgrade_count": m.avg_downgrade_count,
            "over_budget_rate": m.over_budget_rate,
            "avg_duration": m.avg_duration,
            "updated_at": m.updated_at,
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

    # ── Template ───────────────────────────────────────────

    async def _template_list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        if not company_id:
            return {"error": "missing company_id"}
        status = params.get("status")
        templates = await self._template_svc.list_by_company(company_id, status)
        return [
            {
                "template_id": t.template_id,
                "template_scope": t.template_scope,
                "company_id": t.company_id,
                "provider_type": t.provider_type,
                "provider_id": t.provider_id,
                "model": t.model,
                "capability_id": t.capability_id,
                "capability_version": t.capability_version,
                "default_role": t.default_role,
                "version": t.version,
                "status": t.status,
            }
            for t in templates
        ]

    async def _template_get(self, params: dict[str, Any]) -> dict[str, Any]:
        template_id = params.get("template_id")
        if not template_id:
            return {"error": "missing template_id"}
        t = await self._template_svc.get(template_id)
        if t is None:
            return {"error": "not found"}
        return {
            "template_id": t.template_id,
            "template_scope": t.template_scope,
            "company_id": t.company_id,
            "provider_type": t.provider_type,
            "provider_id": t.provider_id,
            "model": t.model,
            "capability_id": t.capability_id,
            "capability_version": t.capability_version,
            "capability_snapshot": t.capability_snapshot,
            "default_role": t.default_role,
            "version": t.version,
            "status": t.status,
        }

    async def _template_create(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        capability_id = params.get("capability_id")
        capability_version = params.get("capability_version", 1)
        default_role = params.get("default_role", "")
        if not company_id or not capability_id:
            return {"error": "missing company_id or capability_id"}

        t = await self._template_svc.create(
            company_id=company_id,
            capability_id=capability_id,
            capability_version=capability_version,
            default_role=default_role,
            capability_snapshot=params.get("capability_snapshot"),
            template_scope=params.get("template_scope", "company"),
            provider_type=params.get("provider_type", "openai"),
            provider_id=params.get("provider_id", "openai"),
            model=params.get("model", "gpt-4"),
        )
        return {"template_id": t.template_id, "version": t.version, "status": t.status}

    async def _template_update(self, params: dict[str, Any]) -> dict[str, Any]:
        template_id = params.get("template_id")
        company_id = params.get("company_id")
        expected_version = params.get("expected_version")
        if not template_id or not company_id or expected_version is None:
            return {"error": "missing template_id/company_id/expected_version"}

        updates = {}
        for key in ("capability_id", "capability_version", "capability_snapshot", "default_role",
                     "provider_type", "provider_id", "model"):
            if key in params:
                updates[key] = params[key]
        if not updates:
            return {"error": "no updates provided"}

        t = await self._template_svc.save_draft(template_id, company_id, expected_version, updates)
        return {"template_id": t.template_id, "version": t.version, "status": t.status}

    async def _template_activate(self, params: dict[str, Any]) -> dict[str, Any]:
        template_id = params.get("template_id")
        company_id = params.get("company_id")
        expected_version = params.get("expected_version")
        if not template_id or not company_id or expected_version is None:
            return {"error": "missing params"}
        t = await self._template_svc.activate(template_id, company_id, expected_version)
        return {"template_id": t.template_id, "version": t.version, "status": t.status}

    async def _template_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        template_id = params.get("template_id")
        company_id = params.get("company_id")
        expected_version = params.get("expected_version")
        if not template_id or not company_id or expected_version is None:
            return {"error": "missing params"}
        t = await self._template_svc.archive(template_id, company_id, expected_version)
        return {"template_id": t.template_id, "version": t.version, "status": t.status}
