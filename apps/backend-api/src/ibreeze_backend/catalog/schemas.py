"""Strict REST contracts for Agent, Model and Provider catalog resources."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentCreate(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=20_000)


class AgentUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=20_000)


class AgentResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    key: str
    catalog_revision: int
    display_name: str
    description: str
    status: Literal["draft", "validated", "published"]
    created_at: datetime
    updated_at: datetime
    version: int


class AgentVersionCreate(StrictModel):
    min_version: str = Field(min_length=1, max_length=64)
    max_version_exclusive: str = Field(min_length=1, max_length=64)
    executable_names: list[str] = Field(min_length=1)
    supported_platforms: list[str] = Field(min_length=1)
    probe_argv: list[str] = Field(min_length=1)
    capability_tags: list[str] = Field(default_factory=list)
    network_domains: list[str] = Field(default_factory=list)
    adapter_contract_version: int = Field(ge=1)


class AgentVersionResponse(AgentVersionCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    agent_id: uuid.UUID
    content_sha256: str
    published_at: datetime | None
    created_at: datetime


class ModelCreate(StrictModel):
    provider_key: str = Field(min_length=1, max_length=64)
    model_key: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=100)
    context_window: int = Field(ge=8192)
    max_output_tokens: int = Field(ge=1)
    tokenizer_key: str = Field(min_length=1, max_length=100)
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    routing_tier: int = Field(ge=0, le=3)
    quality_prior: Decimal = Field(ge=Decimal("0"), le=Decimal("1"), max_digits=5, decimal_places=4)
    tool_reliability_prior: Decimal = Field(ge=Decimal("0"), le=Decimal("1"), max_digits=5, decimal_places=4)
    latency_prior_ms: int = Field(gt=0)
    model_family: str = Field(min_length=1, max_length=100)
    model_vendor: str = Field(min_length=1, max_length=100)
    architecture_class: Literal["dense", "moe", "hybrid", "unknown"]
    supports_reasoning: bool
    reasoning_levels: list[Literal["low", "medium", "high"]]
    input_price_microusd_per_million: int = Field(ge=0)
    output_price_microusd_per_million: int = Field(ge=0)
    routing_enabled: bool

    @field_validator("model_family", "model_vendor")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("MODEL_IDENTITY_REQUIRED")
        return normalized

    @field_validator("reasoning_levels")
    @classmethod
    def normalize_reasoning_levels(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("MODEL_REASONING_LEVELS_DUPLICATE")
        order = {"low": 0, "medium": 1, "high": 2}
        return sorted(value, key=order.__getitem__)

    @model_validator(mode="after")
    def validate_routing_configuration(self) -> ModelCreate:
        if not self.supports_reasoning and self.reasoning_levels:
            raise ValueError("MODEL_REASONING_LEVELS_UNSUPPORTED")
        if self.routing_enabled and (
            self.model_family == "unknown" or self.model_vendor == "unknown"
        ):
            raise ValueError("MODEL_ROUTING_IDENTITY_REQUIRED")
        return self


class ModelUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    context_window: int | None = Field(default=None, ge=8192)
    max_output_tokens: int | None = Field(default=None, ge=1)
    tokenizer_key: str | None = Field(default=None, min_length=1, max_length=100)
    supports_tools: bool | None = None
    supports_streaming: bool | None = None
    supports_vision: bool | None = None
    routing_tier: int | None = Field(default=None, ge=0, le=3)
    quality_prior: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("1"), max_digits=5, decimal_places=4
    )
    tool_reliability_prior: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("1"), max_digits=5, decimal_places=4
    )
    latency_prior_ms: int | None = Field(default=None, gt=0)
    model_family: str | None = Field(default=None, min_length=1, max_length=100)
    model_vendor: str | None = Field(default=None, min_length=1, max_length=100)
    architecture_class: Literal["dense", "moe", "hybrid", "unknown"] | None = None
    supports_reasoning: bool | None = None
    reasoning_levels: list[Literal["low", "medium", "high"]] | None = None
    input_price_microusd_per_million: int | None = Field(default=None, ge=0)
    output_price_microusd_per_million: int | None = Field(default=None, ge=0)
    routing_enabled: bool | None = None

    @field_validator("model_family", "model_vendor")
    @classmethod
    def normalize_optional_identity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("MODEL_IDENTITY_REQUIRED")
        return normalized

    @field_validator("reasoning_levels")
    @classmethod
    def normalize_optional_reasoning_levels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) != len(set(value)):
            raise ValueError("MODEL_REASONING_LEVELS_DUPLICATE")
        order = {"low": 0, "medium": 1, "high": 2}
        return sorted(value, key=order.__getitem__)


class ModelResponse(ModelCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    catalog_revision: int
    status: Literal["draft", "validated", "published"]
    created_at: datetime
    updated_at: datetime
    version: int


class ProviderCreate(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1, max_length=100)
    protocol: Literal[
        "openai_responses",
        "anthropic_messages",
        "openai_chat_completions",
    ]
    base_url: str = Field(min_length=1, max_length=2048)
    auth_scheme: Literal["bearer", "x-api-key"]


class ProviderUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    protocol: Literal[
        "openai_responses",
        "anthropic_messages",
        "openai_chat_completions",
    ] | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    auth_scheme: Literal["bearer", "x-api-key"] | None = None


class ProviderResponse(ProviderCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    catalog_revision: int
    status: Literal["draft", "validated", "published"]
    created_at: datetime
    updated_at: datetime
    version: int


class AgentModelBindingCreate(StrictModel):
    model_id: uuid.UUID
    min_agent_version: str = Field(min_length=1, max_length=64)
    max_agent_version_exclusive: str = Field(min_length=1, max_length=64)


class AgentModelBindingCreateTopLevel(AgentModelBindingCreate):
    agent_id: uuid.UUID


class AgentModelBindingResponse(AgentModelBindingCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime


class ProviderModelBindingCreate(StrictModel):
    model_id: uuid.UUID
    provider_model_name: str = Field(min_length=1, max_length=200)
    request_defaults: dict[str, Any] = Field(default_factory=dict)


class ProviderModelBindingCreateTopLevel(ProviderModelBindingCreate):
    provider_id: uuid.UUID


class ProviderModelBindingResponse(ProviderModelBindingCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    provider_id: uuid.UUID
    created_at: datetime


class CursorPage(StrictModel):
    items: list[Any]
    next_cursor: str | None
