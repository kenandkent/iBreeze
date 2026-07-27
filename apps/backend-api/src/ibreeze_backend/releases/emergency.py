"""Emergency disable service – aligned with design doc G.7."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.emergency_disable import EmergencyDisableRelease
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.releases.emergency")


async def _next_sequence(db: AsyncSession) -> int:
    result = await db.execute(select(EmergencyDisableRelease))
    items = result.scalars().all()
    if not items:
        return 1
    return max(d.sequence for d in items) + 1


async def create_emergency_disable(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    payload_json: dict[str, Any],
    payload_sha256: str,
    signature: str,
    signing_key_id: str,
) -> EmergencyDisableRelease:
    """Create a signed emergency disable release – G.7."""
    logger.info("create_emergency_disable.start", extra={"actor": str(actor_user_id)})
    sequence = await _next_sequence(db)
    release = EmergencyDisableRelease(
        id=uuid.uuid4(),
        sequence=sequence,
        payload_json=payload_json,
        payload_sha256=payload_sha256,
        signature=signature,
        signing_key_id=signing_key_id,
        created_by=actor_user_id,
        created_at=datetime.now(UTC),
    )
    db.add(release)
    await db.flush()
    logger.info("create_emergency_disable.completed", extra={"disable_id": str(release.id), "sequence": sequence})
    return release


async def get_latest_emergency_disable(
    db: AsyncSession,
) -> EmergencyDisableRelease | None:
    """Get the latest emergency disable release."""
    result = await db.execute(
        select(EmergencyDisableRelease).order_by(EmergencyDisableRelease.sequence.desc()).limit(1)
    )
    return result.scalar_one_or_none()
