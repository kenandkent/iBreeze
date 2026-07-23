"""Release management router."""
import uuid
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.catalog_release import CatalogRelease
from ibreeze_backend.releases.emergency import (
    create_emergency_disable,
    get_latest_emergency_disable,
)
from ibreeze_backend.releases.manifest import (
    build_manifest,
    compute_manifest_signature,
    manifest_to_bytes,
)
from ibreeze_backend.security.keys import load_or_create_signing_keys
from ibreeze_backend.settings import settings

admin_router = APIRouter(prefix="/admin/api/v1", tags=["admin-releases"])
public_router = APIRouter(prefix="/api/v1", tags=["releases"])


class ReleaseCreate(BaseModel):
    version: str
    notes: str | None = None


class EmergencyDisableCreate(BaseModel):
    skill_ids: list[str]


async def _next_release_sequence(db: AsyncSession) -> int:
    result = await db.execute(
        select(CatalogRelease).order_by(CatalogRelease.release_sequence.desc()).limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        return 1
    return latest.release_sequence + 1


@admin_router.post(
    "/catalog/releases",
    status_code=status.HTTP_201_CREATED,
)
async def create_release_endpoint(
    body: ReleaseCreate,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    sequence = await _next_release_sequence(db)
    manifest = await build_manifest(db, sequence)

    key_dir = Path(settings.token_secret or "keys")
    private_pem, public_pem, kid = load_or_create_signing_keys(key_dir)
    private_key = serialization.load_pem_private_key(private_pem, password=None)

    manifest_bytes = manifest_to_bytes(manifest)
    signature = compute_manifest_signature(manifest_bytes, private_key)

    manifest["signing_key_id"] = kid
    manifest["signature"] = signature

    release = CatalogRelease(
        version=body.version,
        manifest=manifest,
        notes=body.notes,
        release_sequence=sequence,
        signature=signature,
        signing_key_id=kid,
    )
    db.add(release)
    await db.flush()

    return {
        "id": str(release.id),
        "version": release.version,
        "release_sequence": release.release_sequence,
        "status": release.status,
        "signing_key_id": kid,
    }


@admin_router.post("/catalog/releases/{release_id}/publish")
async def publish_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(CatalogRelease).where(CatalogRelease.id == release_id)
    )
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    if release.status == "published":
        raise HTTPException(status_code=400, detail="Release already published")

    release.status = "published"
    release.published_at = datetime.now(UTC)
    await db.flush()

    return {
        "id": str(release.id),
        "version": release.version,
        "status": release.status,
        "published_at": release.published_at.isoformat(),
    }


@admin_router.post(
    "/emergency-disables",
    status_code=status.HTTP_201_CREATED,
)
async def create_emergency_disable_endpoint(
    body: EmergencyDisableCreate,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    disable = await create_emergency_disable(db, body.skill_ids)
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": disable.disabled_skill_ids,
        "created_at": disable.created_at.isoformat(),
    }


@admin_router.get("/emergency-disables/latest")
async def get_latest_emergency_disable_endpoint(
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    disable = await get_latest_emergency_disable(db)
    if not disable:
        raise HTTPException(status_code=404, detail="No emergency disables found")
    return {
        "id": str(disable.id),
        "sequence": disable.sequence,
        "disabled_skill_ids": disable.disabled_skill_ids,
        "created_at": disable.created_at.isoformat(),
    }


@public_router.get("/catalog/manifest")
async def get_latest_manifest_endpoint(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(
        select(CatalogRelease)
        .where(CatalogRelease.status == "published")
        .order_by(CatalogRelease.release_sequence.desc())
        .limit(1)
    )
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="No published release found")
    return release.manifest


@public_router.get("/catalog/releases/{release_id}")
async def get_release_endpoint(
    release_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await db.execute(
        select(CatalogRelease).where(CatalogRelease.id == release_id)
    )
    release = result.scalar_one_or_none()
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    return {
        "id": str(release.id),
        "version": release.version,
        "manifest": release.manifest,
        "status": release.status,
        "notes": release.notes,
        "release_sequence": release.release_sequence,
        "signing_key_id": release.signing_key_id,
        "published_at": (
            release.published_at.isoformat() if release.published_at else None
        ),
    }
