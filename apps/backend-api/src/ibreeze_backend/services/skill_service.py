"""Skill catalog service."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.skill import Skill


async def create_skill(
    db: AsyncSession,
    name: str,
    version: str,
    category: str,
    description: str | None = None,
    compatibility: dict | None = None,
) -> Skill:
    """Create a new skill."""
    skill = Skill(
        name=name,
        version=version,
        category=category,
        description=description,
        compatibility=compatibility,
    )
    db.add(skill)
    await db.flush()
    return skill


async def get_skill(db: AsyncSession, skill_id: uuid.UUID) -> Skill | None:
    """Get a skill by ID."""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    return result.scalar_one_or_none()


async def list_skills(
    db: AsyncSession,
    category: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[list[Skill], int]:
    """List skills with optional filtering."""
    query = select(Skill)
    count_query = select(func.count(Skill.id))

    if category:
        query = query.where(Skill.category == category)
        count_query = count_query.where(Skill.category == category)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    result = await db.execute(query.offset(skip).limit(limit))
    skills = list(result.scalars().all())
    return skills, total


async def update_skill(
    db: AsyncSession,
    skill: Skill,
    description: str | None = None,
    category: str | None = None,
    compatibility: dict | None = None,
    is_active: bool | None = None,
) -> Skill:
    """Update a skill."""
    if description is not None:
        skill.description = description
    if category is not None:
        skill.category = category
    if compatibility is not None:
        skill.compatibility = compatibility
    if is_active is not None:
        skill.is_active = is_active
    await db.flush()
    return skill


async def check_compatibility(
    skill: Skill,
    min_platform_version: str | None = None,
    max_platform_version: str | None = None,
) -> bool:
    """Check if a skill is compatible with the given platform version."""
    if not skill.compatibility:
        return True

    if min_platform_version and "min_platform" in skill.compatibility:
        if skill.compatibility["min_platform"] > min_platform_version:
            return False

    if max_platform_version and "max_platform" in skill.compatibility:
        if skill.compatibility["max_platform"] < max_platform_version:
            return False

    return True
