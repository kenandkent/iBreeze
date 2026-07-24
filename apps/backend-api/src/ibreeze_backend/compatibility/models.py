"""Canonical compatibility rule model from design section G.6."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class CompatibilityRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compatibility_rules"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('agent','model','skill','client')",
            name="ck_compatibility_subject_type",
        ),
        CheckConstraint(
            "dependency_type IN ('agent','model','skill','platform','client')",
            name="ck_compatibility_dependency_type",
        ),
        CheckConstraint("decision IN ('allow','deny')", name="ck_compatibility_decision"),
        CheckConstraint(
            "status IN ('draft','validated','published')",
            name="ck_compatibility_status",
        ),
        Index("ix_compatibility_subject", "subject_type", "subject_id", "priority"),
    )

    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_version_range: Mapped[str] = mapped_column(String(200), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dependency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    dependency_version_range: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(String(8), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
