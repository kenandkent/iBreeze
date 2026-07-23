"""Skill management router."""
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.services.storage_service import ObjectStorage
from ibreeze_backend.skills.service import install_skill, remove_skill

admin_router = APIRouter(prefix="/admin/api/v1/skills", tags=["admin-skills"])
public_router = APIRouter(prefix="/api/v1/catalog/skills", tags=["skills"])

storage = ObjectStorage()


@admin_router.post(
    "/{skill_id}/versions",
    status_code=status.HTTP_201_CREATED,
)
async def upload_skill_version_endpoint(
    skill_id: str,
    version: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    try:
        uuid.UUID(skill_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID")

    suffix = Path(file.filename).suffix if file.filename else ".zip"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        skill = await install_skill(db, skill_id, version, tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "id": str(skill.id),
        "version": skill.version,
        "checksum": skill.checksum,
        "is_active": skill.is_active,
    }


@public_router.get("/{skill_id}/versions/{version}/package")
async def download_skill_package_endpoint(
    skill_id: str,
    version: str,
    _current_user=Depends(get_current_user),
) -> dict:
    url = storage.get_download_url(skill_id, version)
    if not url:
        raise HTTPException(status_code=404, detail="Package not found")
    return {"download_url": url, "skill_id": skill_id, "version": version}


@admin_router.delete(
    "/{skill_id}/versions/{version}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_skill_version_endpoint(
    skill_id: str,
    version: str,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> None:
    try:
        removed = await remove_skill(db, skill_id, version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not removed:
        raise HTTPException(status_code=404, detail="Skill version not found")
