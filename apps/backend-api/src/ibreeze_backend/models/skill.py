"""Skill entity model – aligned with design doc G.6 + backward-compatible with legacy service."""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Skill revision entity — design doc G.6 + legacy compat columns."""
    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','validated','published','active','disabled')",
            name="ck_skill_status",
        ),
        CheckConstraint("catalog_revision > 0", name="ck_skill_revision"),
    )

    # ── G.6 design doc fields ──────────────────────────────────────────
    key: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    catalog_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    compatibility: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Legacy aliases (service code uses these) ───────────────────────
    @property
    def is_active(self) -> bool:
        return self.status in ("published", "active")

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.status = "published" if value else "draft"

    @property
    def name(self) -> str:
        return self.display_name

    @name.setter
    def name(self, value: str) -> None:
        self.display_name = value


class SkillVersion(UUIDPrimaryKeyMixin, Base):
    """Skill version with package metadata – G.6 skill_versions table."""
    __tablename__ = "skill_versions"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    object_size: Mapped[int] = mapped_column(Integer, nullable=False)
    object_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
