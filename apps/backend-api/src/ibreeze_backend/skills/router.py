"""Canonical Skill catalog routes."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User
from ibreeze_backend.skills.schemas import (
    SkillCreate,
    SkillResponse,
    SkillUpdate,
    SkillVersionResponse,
)
from ibreeze_backend.skills.service import (
    clone_skill_revision,
    create_skill,
    create_skill_version,
    delete_skill,
    delete_skill_version,
    get_skill,
    get_skill_version,
    list_skill_versions,
    list_skills,
    storage,
    update_skill,
    validate_skill,
)

admin_router = APIRouter(prefix="/admin/api/v1/skills", tags=["skills"])
public_router = APIRouter(prefix="/api/v1/catalog/skills", tags=["skills"])


def _version(value: str | None) -> int:
    if value is None:
        raise HTTPException(status_code=428, detail="IF_MATCH_REQUIRED")
    try:
        return int(value.strip('"'))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="IF_MATCH_INVALID") from exc


def _raise(exc: ValueError) -> None:
    code = str(exc)
    if code == "CATALOG_RESOURCE_NOT_FOUND":
        http_status = 404
    elif code in {
        "CATALOG_REVISION_IMMUTABLE",
        "OPTIMISTIC_LOCK_CONFLICT",
        "CATALOG_LOGICAL_KEY_EXISTS",
    }:
        http_status = 409
    else:
        http_status = 422
    raise HTTPException(status_code=http_status, detail=code) from exc


@admin_router.post("", status_code=status.HTTP_201_CREATED, response_model=SkillResponse)
async def create_skill_endpoint(
    body: SkillCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    try:
        item = await create_skill(db, body)
    except ValueError as exc:
        _raise(exc)
    return SkillResponse.model_validate(item)


@admin_router.get("")
async def list_skills_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return {
        "items": [SkillResponse.model_validate(item) for item in await list_skills(db, limit)],
        "next_cursor": None,
    }


@admin_router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill_endpoint(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    item = await get_skill(db, skill_id)
    if item is None:
        raise HTTPException(status_code=404, detail="CATALOG_RESOURCE_NOT_FOUND")
    return SkillResponse.model_validate(item)


@admin_router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill_endpoint(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    try:
        item = await update_skill(db, skill_id, body, _version(if_match))
    except ValueError as exc:
        _raise(exc)
    return SkillResponse.model_validate(item)


@admin_router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_endpoint(
    skill_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        await delete_skill(db, skill_id, _version(if_match))
    except ValueError as exc:
        _raise(exc)
    return Response(status_code=204)


@admin_router.post("/{skill_id}/validate", response_model=SkillResponse)
async def validate_skill_endpoint(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    try:
        item = await validate_skill(db, skill_id)
    except ValueError as exc:
        _raise(exc)
    return SkillResponse.model_validate(item)


@admin_router.post(
    "/{skill_id}/revisions",
    status_code=status.HTTP_201_CREATED,
    response_model=SkillResponse,
)
async def clone_skill_endpoint(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    try:
        item = await clone_skill_revision(db, skill_id)
    except ValueError as exc:
        _raise(exc)
    return SkillResponse.model_validate(item)


@admin_router.post(
    "/{skill_id}/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=SkillVersionResponse,
)
async def upload_skill_version_endpoint(
    skill_id: uuid.UUID,
    version: str = Form(),
    package: UploadFile = File(),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillVersionResponse:
    suffix = Path(package.filename or "").suffix
    if suffix.lower() != ".zip":
        raise HTTPException(status_code=422, detail="SKILL_PACKAGE_EXTENSION_INVALID")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temporary:
        shutil.copyfileobj(package.file, temporary)
        path = Path(temporary.name)
    try:
        item = await create_skill_version(db, skill_id, version, path)
    except ValueError as exc:
        _raise(exc)
    finally:
        path.unlink(missing_ok=True)
    return SkillVersionResponse.model_validate(item)


@admin_router.get("/{skill_id}/versions")
async def list_skill_versions_endpoint(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return {
        "items": [
            SkillVersionResponse.model_validate(item)
            for item in await list_skill_versions(db, skill_id)
        ],
        "next_cursor": None,
    }


@admin_router.delete(
    "/{skill_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_skill_version_endpoint(
    skill_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        await delete_skill_version(db, skill_id, version_id)
    except ValueError as exc:
        _raise(exc)
    return Response(status_code=204)


@public_router.get("/{skill_id}/versions/{version}/package")
async def download_skill_package_endpoint(
    skill_id: uuid.UUID,
    version: str,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> FileResponse:
    item = await get_skill_version(db, skill_id, version)
    path = storage.get_object_path(item.object_key) if item is not None else None
    if path is None:
        raise HTTPException(status_code=404, detail="SKILL_PACKAGE_NOT_FOUND")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{skill_id}-{version}.zip",
    )
