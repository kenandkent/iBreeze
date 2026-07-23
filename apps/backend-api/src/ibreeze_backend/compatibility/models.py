"""Compatibility rule model."""

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CompatibilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compatibility_rules"

    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_version_range: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_version_range: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
