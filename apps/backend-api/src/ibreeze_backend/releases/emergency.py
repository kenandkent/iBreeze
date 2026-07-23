"""Emergency disable service."""
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.emergency_disable import EmergencyDisable
from ibreeze_backend.models.skill import Skill


async def _next_sequence(db: AsyncSession) -> int:
    result = await db.execute(select(EmergencyDisable))
    disables = result.scalars().all()
    if not disables:
        return 1
    return max(d.sequence for d in disables) + 1


async def create_emergency_disable(
    db: AsyncSession, skill_ids: list[str]
) -> EmergencyDisable:
    """Create a signed emergency disable release."""
    for sid in skill_ids:
        result = await db.execute(select(Skill).where(Skill.id == sid))
        skill = result.scalar_one_or_none()
        if skill:
            skill.is_active = False

    sequence = await _next_sequence(db)
    disable = EmergencyDisable(
        sequence=sequence,
        disabled_skill_ids=skill_ids,
        created_at=datetime.now(UTC),
    )
    db.add(disable)
    await db.flush()
    return disable


async def get_latest_emergency_disable(
    db: AsyncSession,
) -> EmergencyDisable | None:
    """Get the latest emergency disable."""
    result = await db.execute(
        select(EmergencyDisable).order_by(EmergencyDisable.sequence.desc()).limit(1)
    )
    return result.scalar_one_or_none()
