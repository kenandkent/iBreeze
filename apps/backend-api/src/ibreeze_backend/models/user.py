"""User model for backend API – aligned with design doc G.3."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(user_type = 'admin' AND username IS NOT NULL) "
            "OR (user_type = 'app_user' AND (email IS NOT NULL OR username IS NOT NULL))",
            name="ck_user_type_fields",
        ),
        CheckConstraint("NOT protected OR user_type = 'admin'", name="ck_protected_admin"),
        Index("ix_users_type_status", "user_type", "status", "created_at", "id"),
    )

    user_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # admin | app_user
    username: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active | disabled
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    failed_login_count: Mapped[int] = mapped_column(nullable=False, default=0)
    locked_until: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_login_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)

    # --- backward-compatible aliases for existing code ---

    @property
    def hashed_password(self) -> str:
        return self.password_hash

    @hashed_password.setter
    def hashed_password(self, value: str) -> None:
        self.password_hash = value

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self.status = "active" if value else "disabled"

    @property
    def role(self) -> str | None:
        return self.user_type

    @role.setter
    def role(self, value: str) -> None:
        self.user_type = value


@event.listens_for(User, "init")
def _user_default_display_name(target, args, kwargs):
    """Auto-fill display_name from email or username if not provided."""
    if not kwargs.get("display_name"):
        kwargs["display_name"] = kwargs.get("email") or kwargs.get("username") or ""
