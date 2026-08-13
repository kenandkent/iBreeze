"""Canonical catalog persistence models from design section G.6."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CatalogRevisionMixin(TimestampMixin):
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AgentCatalog(UUIDPrimaryKeyMixin, CatalogRevisionMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("key", "catalog_revision", name="uq_agents_key_revision"),
        CheckConstraint("catalog_revision > 0", name="ck_agents_revision"),
        CheckConstraint(
            "status IN ('draft','validated','published')",
            name="ck_agents_status",
        ),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class AgentVersionRange(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "min_version",
            "max_version_exclusive",
            name="uq_agent_version_range",
        ),
        CheckConstraint("min_version <> max_version_exclusive", name="ck_agent_version_nonempty"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    min_version: Mapped[str] = mapped_column(String(64), nullable=False)
    max_version_exclusive: Mapped[str] = mapped_column(String(64), nullable=False)
    executable_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    supported_platforms: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    probe_argv: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    capability_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    network_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    adapter_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ModelCatalog(UUIDPrimaryKeyMixin, CatalogRevisionMixin, Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint(
            "provider_key",
            "model_key",
            "catalog_revision",
            name="uq_models_logical_revision",
        ),
        CheckConstraint("catalog_revision > 0", name="ck_models_revision"),
        CheckConstraint("context_window > 0", name="ck_models_context_window"),
        CheckConstraint("max_output_tokens > 0", name="ck_models_max_output"),
        CheckConstraint("routing_tier >= 0 AND routing_tier <= 3", name="ck_models_routing_tier"),
        CheckConstraint("quality_prior >= 0 AND quality_prior <= 1", name="ck_models_quality_prior"),
        CheckConstraint(
            "tool_reliability_prior >= 0 AND tool_reliability_prior <= 1",
            name="ck_models_tool_reliability_prior",
        ),
        CheckConstraint("latency_prior_ms > 0", name="ck_models_latency_prior"),
        CheckConstraint(
            "architecture_class IN ('dense','moe','hybrid','unknown')",
            name="ck_models_architecture_class",
        ),
        CheckConstraint("input_price_microusd_per_million >= 0", name="ck_models_input_price"),
        CheckConstraint("output_price_microusd_per_million >= 0", name="ck_models_output_price"),
        CheckConstraint(
            "supports_reasoning OR jsonb_array_length(reasoning_levels) = 0",
            name="ck_models_reasoning_levels",
        ),
        CheckConstraint(
            "NOT routing_enabled OR (model_family <> 'unknown' AND model_vendor <> 'unknown')",
            name="ck_models_routing_identity",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published')",
            name="ck_models_status",
        ),
    )

    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model_key: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    tokenizer_key: Mapped[str] = mapped_column(String(100), nullable=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False)
    routing_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    quality_prior: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.5, server_default="0.5"
    )
    tool_reliability_prior: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.5, server_default="0.5"
    )
    latency_prior_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=3000, server_default="3000")
    model_family: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown", server_default="unknown")
    model_vendor: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown", server_default="unknown")
    architecture_class: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default="unknown"
    )
    supports_reasoning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    reasoning_levels: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    input_price_microusd_per_million: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    output_price_microusd_per_million: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    routing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class ProviderCatalog(UUIDPrimaryKeyMixin, CatalogRevisionMixin, Base):
    __tablename__ = "api_providers"
    __table_args__ = (
        UniqueConstraint("key", "catalog_revision", name="uq_providers_key_revision"),
        CheckConstraint("catalog_revision > 0", name="ck_providers_revision"),
        CheckConstraint(
            "protocol IN ('openai_responses','anthropic_messages','openai_chat_completions')",
            name="ck_providers_protocol",
        ),
        CheckConstraint(
            "auth_scheme IN ('bearer','x-api-key')",
            name="ck_providers_auth_scheme",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published')",
            name="ck_providers_status",
        ),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_scheme: Mapped[str] = mapped_column(String(32), nullable=False)


class AgentModelBinding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_model_bindings"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "model_id",
            "min_agent_version",
            "max_agent_version_exclusive",
            name="uq_agent_model_binding_range",
        ),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id"),
        nullable=False,
    )
    min_agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    max_agent_version_exclusive: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProviderModelBinding(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "provider_model_bindings"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_id", name="uq_provider_model_binding"),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("models.id"),
        nullable=False,
    )
    provider_model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    request_defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
