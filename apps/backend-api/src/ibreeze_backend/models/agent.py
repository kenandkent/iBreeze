"""Agent entity model for catalog – aligned with design doc G.6."""
import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Agent revision (catalog_revision) – G.6 agents table."""
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','validated','published')", name="ck_agent_status"
        ),
        CheckConstraint("catalog_revision > 0", name="ck_agent_revision"),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AgentVersion(UUIDPrimaryKeyMixin, Base):
    """Agent version with platform metadata – G.6 agent_versions table."""
    __tablename__ = "agent_versions"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    min_version: Mapped[str] = mapped_column(String(64), nullable=False)
    max_version_exclusive: Mapped[str] = mapped_column(String(64), nullable=False)
    executable_names: Mapped[dict] = mapped_column(JSONB, nullable=False)
    supported_platforms: Mapped[dict] = mapped_column(JSONB, nullable=False)
    probe_argv: Mapped[dict] = mapped_column(JSONB, nullable=False)
    capability_tags: Mapped[dict] = mapped_column(JSONB, nullable=False)
    network_domains: Mapped[dict] = mapped_column(JSONB, nullable=False)
    adapter_contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class AgentModelBinding(UUIDPrimaryKeyMixin, Base):
    """Binding between agent version range and model – G.6 agent_model_bindings."""
    __tablename__ = "agent_model_bindings"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    min_agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    max_agent_version_exclusive: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
