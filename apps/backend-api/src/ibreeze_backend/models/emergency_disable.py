"""Emergency disable model."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class EmergencyDisable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "emergency_disables"

    sequence: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    disabled_skill_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
