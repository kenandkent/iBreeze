"""Skill package management service."""
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.skill import Skill
from ibreeze_backend.services.storage_service import ObjectStorage
from ibreeze_backend.services.zip_service import (
    compute_zip_checksum,
    validate_uncompressed_size,
    validate_zip_size,
    validate_zip_structure,
)

storage = ObjectStorage()


async def install_skill(
    db: AsyncSession, skill_id: str, version: str, zip_path: Path
) -> Skill:
    ok, errors = validate_zip_structure(zip_path)
    if not ok:
        raise ValueError(f"Invalid ZIP: {', '.join(errors)}")

    if not validate_zip_size(zip_path):
        raise ValueError("ZIP exceeds 50 MiB upload limit")

    if not validate_uncompressed_size(zip_path):
        raise ValueError("ZIP exceeds 200 MiB uncompressed limit")

    checksum = compute_zip_checksum(zip_path)

    result = await db.execute(
        select(Skill).where(Skill.id == uuid.UUID(skill_id))
    )
    all_versions = result.scalars().all()

    existing = next((s for s in all_versions if s.version == version), None)

    if existing:
        if existing.is_active:
            raise ValueError("Version already installed and active")
        existing.is_active = True
        existing.checksum = checksum
        storage.store(skill_id, version, zip_path)
        await db.flush()
        return existing

    base_skill = all_versions[0] if all_versions else None

    storage.store(skill_id, version, zip_path)

    skill = Skill(
        id=uuid.UUID(skill_id),
        name=base_skill.name if base_skill else skill_id,
        version=version,
        category=base_skill.category if base_skill else "general",
        description=base_skill.description if base_skill else None,
        compatibility=base_skill.compatibility if base_skill else None,
        is_active=True,
        checksum=checksum,
    )
    db.add(skill)
    await db.flush()
    return skill


async def remove_skill(
    db: AsyncSession, skill_id: str, version: str
) -> bool:
    """Remove a skill version. Only if no active references."""
    result = await db.execute(
        select(Skill).where(
            Skill.id == uuid.UUID(skill_id),
            Skill.version == version,
        )
    )
    skill = result.scalar_one_or_none()
    if not skill:
        return False

    if not skill.is_active:
        storage.delete(skill_id, version)
        await db.delete(skill)
        await db.flush()
        return True

    raise ValueError("Cannot remove active version; disable it first")


async def emergency_disable_skill(
    db: AsyncSession, skill_id: str
) -> bool:
    """Set status to disabled, keep package in storage."""
    result = await db.execute(select(Skill).where(Skill.id == uuid.UUID(skill_id)))
    skill = result.scalar_one_or_none()
    if not skill:
        return False
    skill.is_active = False
    await db.flush()
    return True
