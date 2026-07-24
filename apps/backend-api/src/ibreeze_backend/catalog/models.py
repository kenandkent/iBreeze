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
