"""Central user model defined by design section G.3."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    user_type: Mapped[str] = mapped_column(String(16), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "user_type IN ('admin', 'app_user')",
            name="ck_users_type",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_users_status",
        ),
        CheckConstraint(
            "(user_type = 'admin' AND username IS NOT NULL AND email IS NULL) "
            "OR (user_type = 'app_user' AND email IS NOT NULL AND username IS NULL)",
            name="ck_users_identity",
        ),
        CheckConstraint(
            "NOT protected OR user_type = 'admin'",
            name="ck_users_protected_admin",
        ),
        CheckConstraint(
            "failed_login_count >= 0",
            name="ck_users_failed_login_count",
        ),
        CheckConstraint("version > 0", name="ck_users_version"),
        Index(
            "uq_users_username_lower",
            func.lower(username),
            unique=True,
            postgresql_where=username.is_not(None),
        ),
        Index(
            "uq_users_email_lower",
            func.lower(email),
            unique=True,
            postgresql_where=email.is_not(None),
        ),
        Index("ix_users_type_status", "user_type", "status", "created_at", "id"),
    )
