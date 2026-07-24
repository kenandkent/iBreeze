"""Immutable Catalog Release models from design section G.7."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import UUIDPrimaryKeyMixin


class CatalogRelease(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "catalog_releases"
    __table_args__ = (
        CheckConstraint("release_sequence > 0", name="ck_release_sequence"),
        CheckConstraint(
            "status IN ('publishing','published','failed')",
            name="ck_release_status",
        ),
    )

    release_sequence: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    minimum_client_version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_object_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogReleaseItem(Base):
    __tablename__ = "catalog_release_items"
    __table_args__ = (
        CheckConstraint(
            """resource_type IN (
                'agent_revision','agent_version','model','provider',
                'skill_revision','skill_version','compatibility_rule'
            )""",
            name="ck_release_item_type",
        ),
    )

    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("catalog_releases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    resource_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    resource_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
