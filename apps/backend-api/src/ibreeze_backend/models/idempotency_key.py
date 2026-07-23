"""API idempotency model – aligned with design doc G.3."""
import uuid

from sqlalchemy import Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import UUIDPrimaryKeyMixin


class ApiIdempotency(UUIDPrimaryKeyMixin, Base):
    """API idempotency – G.3 api_idempotency table."""
    __tablename__ = "api_idempotency"

    principal_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_content_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)
