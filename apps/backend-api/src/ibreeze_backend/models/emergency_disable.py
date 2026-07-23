"""Emergency disable release model – aligned with design doc G.7."""
import uuid

from sqlalchemy import BigInteger, CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ibreeze_backend.db.session import Base
from ibreeze_backend.models.base import UUIDPrimaryKeyMixin


class EmergencyDisableRelease(UUIDPrimaryKeyMixin, Base):
    """Emergency disable release – G.7 emergency_disable_releases table."""
    __tablename__ = "emergency_disable_releases"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_ed_sequence"),
    )

    sequence: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
