"""Skill catalog revisions and signed package versions."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.skill import Skill, SkillVersion
from ibreeze_backend.security.keys import load_or_create_signing_keys
from ibreeze_backend.services.storage_service import ObjectStorage
from ibreeze_backend.services.zip_service import validate_skill_zip
from ibreeze_backend.settings import settings
from ibreeze_backend.skills.schemas import SkillCreate, SkillUpdate

storage = ObjectStorage()


async def create_skill(db: AsyncSession, body: SkillCreate) -> Skill:
    exists = await db.scalar(select(func.count()).select_from(Skill).where(Skill.key == body.key))
    if exists:
        raise ValueError("CATALOG_LOGICAL_KEY_EXISTS")
    item = Skill(**body.model_dump(), catalog_revision=1, status="draft", version=1)
    db.add(item)
    await db.flush()
    return item


async def get_skill(db: AsyncSession, skill_id: uuid.UUID) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    return result.scalar_one_or_none()


async def list_skills(db: AsyncSession, limit: int = 50) -> list[Skill]:
    return list(
        await db.scalars(select(Skill).order_by(Skill.created_at.desc()).limit(limit))
    )


async def update_skill(
    db: AsyncSession,
    skill_id: uuid.UUID,
    body: SkillUpdate,
    expected_version: int,
) -> Skill:
    item = await _locked_skill(db, skill_id)
    _assert_mutable(item)
    _assert_version(item, expected_version)
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(item, name, value)
    item.status = "draft"
    item.version += 1
    await db.flush()
    return item


async def delete_skill(db: AsyncSession, skill_id: uuid.UUID, expected_version: int) -> None:
    item = await _locked_skill(db, skill_id)
    _assert_mutable(item)
    _assert_version(item, expected_version)
    versions = list(await db.scalars(select(SkillVersion).where(SkillVersion.skill_id == skill_id)))
    await db.delete(item)
    await db.flush()
    for version in versions:
        storage.delete_object(version.object_key)


async def validate_skill(db: AsyncSession, skill_id: uuid.UUID) -> Skill:
    item = await _locked_skill(db, skill_id)
    _assert_mutable(item)
    count = await db.scalar(
        select(func.count()).select_from(SkillVersion).where(SkillVersion.skill_id == skill_id)
    )
    if not count:
        raise ValueError("SKILL_VERSION_REQUIRED")
    item.status = "validated"
    await db.flush()
    return item


async def clone_skill_revision(db: AsyncSession, skill_id: uuid.UUID) -> Skill:
    source = await _locked_skill(db, skill_id)
    if source.status != "published":
        raise ValueError("CATALOG_REVISION_SOURCE_NOT_PUBLISHED")
    revision = (
        await db.scalar(select(func.max(Skill.catalog_revision)).where(Skill.key == source.key))
        or 0
    ) + 1
    clone = Skill(
        key=source.key,
        catalog_revision=revision,
        display_name=source.display_name,
        description=source.description,
        status="draft",
        version=1,
    )
    db.add(clone)
    await db.flush()
    versions = await db.scalars(select(SkillVersion).where(SkillVersion.skill_id == source.id))
    for source_version in versions:
        object_key = (
            f"skills/{clone.id}/{source_version.version}/{source_version.object_sha256}.zip"
        )
        storage.copy_object(source_version.object_key, object_key)
        clone_version = SkillVersion(
            skill_id=clone.id,
            version=source_version.version,
            manifest_json=source_version.manifest_json,
            object_key=object_key,
            object_size=source_version.object_size,
            object_sha256=source_version.object_sha256,
            signature="",
            signing_key_id="",
            content_sha256=source_version.content_sha256,
        )
        _sign_version(clone_version)
        db.add(clone_version)
    await db.flush()
    return clone


async def create_skill_version(
    db: AsyncSession,
    skill_id: uuid.UUID,
    version: str,
    package_path: Path,
) -> SkillVersion:
    skill = await _locked_skill(db, skill_id)
    _assert_mutable(skill)
    manifest, object_sha256, content_sha256 = validate_skill_zip(
        package_path,
        expected_key=skill.key,
        expected_version=version,
    )
    object_key = f"skills/{skill.id}/{version}/{object_sha256}.zip"
    storage.put_object(object_key, package_path)
    item = SkillVersion(
        skill_id=skill.id,
        version=version,
        manifest_json=manifest.model_dump(mode="json"),
        object_key=object_key,
        object_size=package_path.stat().st_size,
        object_sha256=object_sha256,
        signature="",
        signing_key_id="",
        content_sha256=content_sha256,
    )
    _sign_version(item)
    db.add(item)
    skill.status = "draft"
    skill.version += 1
    await db.flush()
    return item


async def list_skill_versions(db: AsyncSession, skill_id: uuid.UUID) -> list[SkillVersion]:
    return list(
        await db.scalars(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.created_at)
        )
    )


async def delete_skill_version(
    db: AsyncSession,
    skill_id: uuid.UUID,
    version_id: uuid.UUID,
) -> None:
    skill = await _locked_skill(db, skill_id)
    _assert_mutable(skill)
    result = await db.execute(
        select(SkillVersion)
        .where(SkillVersion.id == version_id, SkillVersion.skill_id == skill_id)
        .with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None or item.published_at is not None:
        raise ValueError("CATALOG_CHILD_IMMUTABLE_OR_MISSING")
    object_key = item.object_key
    await db.delete(item)
    skill.status = "draft"
    skill.version += 1
    await db.flush()
    storage.delete_object(object_key)


async def get_skill_version(
    db: AsyncSession,
    skill_id: uuid.UUID,
    version: str,
) -> SkillVersion | None:
    result = await db.execute(
        select(SkillVersion).where(
            SkillVersion.skill_id == skill_id,
            SkillVersion.version == version,
        )
    )
    return result.scalar_one_or_none()


def _sign_version(item: SkillVersion) -> None:
    private_pem, _public_pem, kid = load_or_create_signing_keys(
        Path(settings.catalog_key_dir)
    )
    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("CATALOG_SIGNING_KEY_INVALID")
    payload = (
        f"skill-v1\n{item.skill_id}\n{item.version}\n"
        f"{item.object_sha256}\n{item.content_sha256}"
    ).encode("ascii")
    item.signature = base64.urlsafe_b64encode(key.sign(payload)).rstrip(b"=").decode()
    item.signing_key_id = kid


async def _locked_skill(db: AsyncSession, skill_id: uuid.UUID) -> Skill:
    result = await db.execute(
        select(Skill).where(Skill.id == skill_id).with_for_update()
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise ValueError("CATALOG_RESOURCE_NOT_FOUND")
    return item


def _assert_mutable(item: Skill) -> None:
    if item.status == "published":
        raise ValueError("CATALOG_REVISION_IMMUTABLE")


def _assert_version(item: Skill, expected_version: int) -> None:
    if item.version != expected_version:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")
