"""Skill / PromptAsset / Capability 领域模型。"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any


def compute_checksum(data: dict[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class PromptAsset:
    prompt_asset_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_scope: str = "company"
    company_id: str | None = None
    name: str = ""
    segments: dict = field(default_factory=dict)
    variables: list[dict] = field(default_factory=list)
    context_slots: list[str] = field(default_factory=list)
    checksum: str = ""
    version: int = 1
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""

    def compute_checksum(self) -> str:
        return compute_checksum(
            {
                "name": self.name,
                "segments": self.segments,
                "variables": self.variables,
                "context_slots": self.context_slots,
            }
        )


@dataclass
class Skill:
    skill_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_scope: str = "company"
    company_id: str | None = None
    name: str = ""
    prompt_asset_id: str = ""
    prompt_asset_version: int = 0
    prompt_asset_checksum: str = ""
    tool_bindings: list[dict] = field(default_factory=list)
    knowledge_refs: list[str] = field(default_factory=list)
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    checksum: str = ""
    version: int = 1
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""

    def compute_checksum(self) -> str:
        return compute_checksum(
            {
                "name": self.name,
                "prompt_asset_id": self.prompt_asset_id,
                "prompt_asset_version": self.prompt_asset_version,
                "tool_bindings": self.tool_bindings,
                "knowledge_refs": self.knowledge_refs,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
            }
        )


@dataclass
class Capability:
    capability_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_scope: str = "company"
    company_id: str | None = None
    name: str = ""
    description: str = ""
    source_category: str = "custom"
    visibility: str = "company"
    cost_policy: dict = field(default_factory=dict)
    checksum: str = ""
    version: int = 1
    status: str = "draft"
    created_at: str = ""
    updated_at: str = ""
