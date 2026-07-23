"""Catalog release service."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.catalog_release import CatalogRelease
from ibreeze_backend.models.skill import Skill


async def generate_manifest(db: AsyncSession) -> dict:
    """Generate catalog manifest from active skills."""
    result = await db.execute(select(Skill).where(Skill.status.in_(["published", "active"])))
    skills = result.scalars().all()

    manifest = {
        "version": datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skills": [],
    }

    for skill in skills:
        manifest["skills"].append({
            "id": str(skill.id),
            "name": skill.name,
            "version": skill.version,
            "category": skill.category,
            "compatibility": skill.compatibility,
        })

    return manifest


async def create_release(
    db: AsyncSession,
    version: str,
    notes: str | None = None,
) -> CatalogRelease:
    """Create a new catalog release."""
    manifest = await generate_manifest(db)
    release = CatalogRelease(
        version=version,
        manifest=manifest,
        notes=notes,
    )
    db.add(release)
    await db.flush()
    return release


async def publish_release(
    db: AsyncSession, release_id: uuid.UUID
) -> CatalogRelease | None:
    """Publish a catalog release."""
    result = await db.execute(
        select(CatalogRelease).where(CatalogRelease.id == release_id)
    )
    release = result.scalar_one_or_none()
    if not release:
        return None
    release.status = "published"
    release.published_at = datetime.now(timezone.utc)
    await db.flush()
    return release


async def emergency_disable_skill(
    db: AsyncSession, skill_id: uuid.UUID
) -> bool:
    """Emergency disable a skill."""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        return False
    skill.is_active = False
    await db.flush()
    return True
