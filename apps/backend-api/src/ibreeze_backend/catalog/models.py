"""Catalog models."""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class AgentCatalog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_catalog"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class AgentVersionRange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_version_ranges"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_catalog.id"), nullable=False
    )
    executable_names: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    supported_platforms: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    min_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_version_exclusive: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    probe_command: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    capability_tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    network_domains: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    adapter_contract_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ModelCatalog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_catalog"

    provider_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_tools: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    supports_vision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class ProviderCatalog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_catalog"

    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")


class AgentModelBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_model_bindings"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_catalog.id"), nullable=False
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_catalog.id"), nullable=False
    )
    agent_version_range: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ProviderModelBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_model_bindings"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_catalog.id"), nullable=False
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_catalog.id"), nullable=False
    )
    api_protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
