"""Refresh token family and token models – aligned with design doc G.3."""
import uuid

from sqlalchemy import BigInteger, CheckConstraint, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import UUIDPrimaryKeyMixin


class RefreshTokenFamily(UUIDPrimaryKeyMixin, Base):
    """Refresh token family – G.3 refresh_token_families table.

    Legacy aliases:
      family_id -> id
      status -> revoked_at is None means active
      refresh_token_hash -> removed (use refresh_tokens table)
      rotated_at -> last_used_at
    """
    __tablename__ = "refresh_token_families"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_used_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revoked_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @property
    def family_id(self) -> str:
        return str(self.id)

    @family_id.setter
    def family_id(self, value: str) -> None:
        import uuid as _uuid
        if isinstance(value, str):
            self.id = _uuid.UUID(value)
        else:
            self.id = value

    @property
    def status(self) -> str:
        return "active" if self.revoked_at is None else "revoked"

    @status.setter
    def status(self, value: str) -> None:
        if value in ("revoked", "rotated"):
            if self.last_used_at:
                self.revoked_at = self.last_used_at
        elif value == "active":
            self.revoked_at = None

    @property
    def refresh_token_hash(self) -> str | None:
        return None

    @refresh_token_hash.setter
    def refresh_token_hash(self, value: str | None) -> None:
        pass

    @property
    def rotated_at(self) -> str | None:
        return self.last_used_at

    @rotated_at.setter
    def rotated_at(self, value: str) -> None:
        self.last_used_at = value


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Refresh token – G.3 refresh_tokens table."""
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index(
            "ix_refresh_tokens_family_active",
            "family_id",
            "expires_at",
            postgresql_where="revoked_at IS NULL",
        ),
    )

    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    issued_at: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)
    consumed_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    revoked_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
