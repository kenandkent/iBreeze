"""Catalog release model."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CatalogRelease(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "catalog_releases"

    version: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    release_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    signing_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
