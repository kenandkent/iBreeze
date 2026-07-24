"""Strict Skill revision and package manifest contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillCreate(StrictModel):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=20_000)


class SkillUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=20_000)


class SkillResponse(SkillCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    catalog_revision: int
    status: Literal["draft", "validated", "published"]
    created_at: datetime
    updated_at: datetime
    version: int


class Dependency(StrictModel):
    skill_key: str = Field(min_length=1, max_length=100)
    version_range: str = Field(min_length=1, max_length=200)


class ModelRequirements(StrictModel):
    supports_tools: bool
    supports_vision: bool
    minimum_context_window: int = Field(ge=8192)


class ManifestFile(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executable: bool
    interpreter: Literal["python3", "zsh"] | None


class SkillManifest(StrictModel):
    schema_version: Literal[1]
    key: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=20_000)
    entrypoint: str
    capability_tags: list[str]
    supported_runtime_types: list[Literal["agent_cli", "api_model"]] = Field(min_length=1)
    supported_agent_keys: list[str]
    model_requirements: ModelRequirements
    supported_platforms: list[str] = Field(min_length=1)
    required_tools: list[str]
    network_domains: list[str]
    file_policy: Literal["workspace_rw_external_ro"]
    risk_level: Literal["low", "medium", "high"]
    dependencies: list[Dependency]
    conflicts: list[Dependency]
    files: list[ManifestFile] = Field(min_length=1)


class SkillVersionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    skill_id: uuid.UUID
    version: str
    manifest_json: dict[str, object]
    object_key: str
    object_size: int
    object_sha256: str
    signature: str
    signing_key_id: str
    content_sha256: str
    published_at: datetime | None
    created_at: datetime
