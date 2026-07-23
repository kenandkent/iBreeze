"""Model entity for catalog – aligned with design doc G.6."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Model(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Model revision (catalog_revision) – G.6 models table."""
    __tablename__ = "models"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','validated','published')", name="ck_model_status"
        ),
        CheckConstraint("catalog_revision > 0", name="ck_model_revision"),
        CheckConstraint("context_window > 0", name="ck_model_context_window"),
        CheckConstraint("max_output_tokens > 0", name="ck_model_max_output"),
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
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ProviderModelBinding(UUIDPrimaryKeyMixin, Base):
    """Binding between provider and model – G.6 provider_model_bindings."""
    __tablename__ = "provider_model_bindings"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    provider_model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    request_defaults: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
