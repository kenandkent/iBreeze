"""ApiProvider entity for catalog – aligned with design doc G.6."""
import uuid

from sqlalchemy import CheckConstraint, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ApiProvider(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """ApiProvider revision (catalog_revision) – G.6 api_providers table."""
    __tablename__ = "api_providers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','validated','published')", name="ck_provider_status"
        ),
        CheckConstraint(
            "protocol IN ('openai_responses','anthropic_messages','openai_chat_completions')",
            name="ck_provider_protocol",
        ),
        CheckConstraint(
            "auth_scheme IN ('bearer','x-api-key')",
            name="ck_provider_auth_scheme",
        ),
        CheckConstraint("catalog_revision > 0", name="ck_provider_revision"),
    )

    key: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    auth_scheme: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
