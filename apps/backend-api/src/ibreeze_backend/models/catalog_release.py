"""Catalog release and item models – aligned with design doc G.7 + legacy compat."""
from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, CheckConstraint, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import UUIDPrimaryKeyMixin


class CatalogRelease(UUIDPrimaryKeyMixin, Base):
    """Catalog release – G.7 catalog_releases table + legacy compat fields."""
    __tablename__ = "catalog_releases"
    __table_args__ = (
        CheckConstraint("release_sequence > 0", name="ck_release_sequence"),
        CheckConstraint(
            "status IN ('draft','publishing','published','failed')",
            name="ck_release_status",
        ),
    )

    release_sequence: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    minimum_client_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="0.0.0"
    )
    manifest_object_key: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, default=""
    )
    manifest_sha256: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    signature: Mapped[str] = mapped_column(Text, nullable=False, default="")
    signing_key_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default=""
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    published_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Legacy compat properties (router uses these) ───────────────────
    @property
    def version(self) -> str:
        return self.minimum_client_version

    @version.setter
    def version(self, value: str) -> None:
        self.minimum_client_version = value

    @property
    def manifest(self) -> dict:
        return {}

    @manifest.setter
    def manifest(self, value: dict) -> None:
        pass


class CatalogReleaseItem(UUIDPrimaryKeyMixin, Base):
    """Item within a catalog release – G.7 catalog_release_items table."""
    __tablename__ = "catalog_release_items"

    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    resource_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
