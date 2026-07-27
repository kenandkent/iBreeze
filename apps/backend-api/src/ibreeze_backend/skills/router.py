"""Canonical Skill catalog routes."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.api.errors import raise_problem
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User
from ibreeze_backend.observability.logging_config import get_logger
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

logger = get_logger("ibreeze.skills")

admin_router = APIRouter(prefix="/admin/api/v1/skills", tags=["skills"])
public_router = APIRouter(prefix="/api/v1/catalog/skills", tags=["skills"])


def _version(value: str | None) -> int:
    if value is None:
        raise_problem(428, "IF_MATCH_REQUIRED", "If-Match header required")
        return 0
    try:
        return int(value.strip('"'))
    except ValueError:
        raise_problem(400, "IF_MATCH_INVALID", "If-Match header invalid")
        return 0


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
    raise_problem(http_status, code, code)


@admin_router.post("", status_code=status.HTTP_201_CREATED, response_model=SkillResponse)
async def create_skill_endpoint(
    body: SkillCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    logger.info("create_skill.start", extra={"key": body.key})
    try:
        item = await create_skill(db, body)
        logger.info("create_skill.completed", extra={"skill_id": str(item.id), "key": body.key})
    except ValueError as exc:
        logger.error("create_skill.failed", extra={"key": body.key, "error": str(exc)})
        _raise(exc)
    return SkillResponse.model_validate(item)


@admin_router.get("")
async def list_skills_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("list_skills.start", extra={"limit": limit})
    items = [SkillResponse.model_validate(item) for item in await list_skills(db, limit)]
    result: dict[str, object] = {"items": items, "next_cursor": None}
    logger.info("list_skills.completed", extra={"count": len(items)})
    return result


@admin_router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill_endpoint(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    logger.info("get_skill.start", extra={"skill_id": str(skill_id)})
    item = await get_skill(db, skill_id)
    if item is None:
        logger.warning("get_skill.failed", extra={"skill_id": str(skill_id), "reason": "not_found"})
        raise_problem(404, "CATALOG_RESOURCE_NOT_FOUND", "Resource not found")
    return SkillResponse.model_validate(item)


@admin_router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill_endpoint(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    logger.info("update_skill.start", extra={"skill_id": str(skill_id)})
    try:
        item = await update_skill(db, skill_id, body, _version(if_match))
        logger.info("update_skill.completed", extra={"skill_id": str(skill_id)})
    except ValueError as exc:
        logger.error("update_skill.failed", extra={"skill_id": str(skill_id), "error": str(exc)})
        _raise(exc)
    return SkillResponse.model_validate(item)


@admin_router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_endpoint(
    skill_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    logger.info("delete_skill.start", extra={"skill_id": str(skill_id)})
    try:
        await delete_skill(db, skill_id, _version(if_match))
        logger.info("delete_skill.completed", extra={"skill_id": str(skill_id)})
    except ValueError as exc:
        logger.error("delete_skill.failed", extra={"skill_id": str(skill_id), "error": str(exc)})
        _raise(exc)
    return Response(status_code=204)


@admin_router.post("/{skill_id}/validate", response_model=SkillResponse)
async def validate_skill_endpoint(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> SkillResponse:
    logger.info("validate_skill.start", extra={"skill_id": str(skill_id)})
    try:
        item = await validate_skill(db, skill_id)
        logger.info("validate_skill.completed", extra={"skill_id": str(skill_id)})
    except ValueError as exc:
        logger.error("validate_skill.failed", extra={"skill_id": str(skill_id), "error": str(exc)})
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
    logger.info("clone_skill.start", extra={"skill_id": str(skill_id)})
    try:
        item = await clone_skill_revision(db, skill_id)
        logger.info("clone_skill.completed", extra={"skill_id": str(skill_id), "clone_id": str(item.id)})
    except ValueError as exc:
        logger.error("clone_skill.failed", extra={"skill_id": str(skill_id), "error": str(exc)})
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
    logger.info("upload_skill_version.start", extra={"skill_id": str(skill_id), "version": version})
    suffix = Path(package.filename or "").suffix
    if suffix.lower() != ".zip":
        logger.error(
            "upload_skill_version.failed",
            extra={"skill_id": str(skill_id), "error": "SKILL_PACKAGE_EXTENSION_INVALID"},
        )
        raise_problem(422, "SKILL_PACKAGE_EXTENSION_INVALID", "Package must have a .zip extension")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temporary:
        shutil.copyfileobj(package.file, temporary)
        path = Path(temporary.name)
    try:
        item = await create_skill_version(db, skill_id, version, path)
        logger.info("upload_skill_version.completed", extra={"skill_id": str(skill_id), "version": version})
    except ValueError as exc:
        logger.error(
            "upload_skill_version.failed",
            extra={"skill_id": str(skill_id), "version": version, "error": str(exc)},
        )
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
    logger.info("list_skill_versions.start", extra={"skill_id": str(skill_id)})
    items = [
        SkillVersionResponse.model_validate(item)
        for item in await list_skill_versions(db, skill_id)
    ]
    result: dict[str, object] = {"items": items, "next_cursor": None}
    logger.info("list_skill_versions.completed", extra={"skill_id": str(skill_id), "count": len(items)})
    return result


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
    logger.info("delete_skill_version.start", extra={"skill_id": str(skill_id), "version_id": str(version_id)})
    try:
        await delete_skill_version(db, skill_id, version_id)
        logger.info("delete_skill_version.completed", extra={"skill_id": str(skill_id), "version_id": str(version_id)})
    except ValueError as exc:
        logger.error(
            "delete_skill_version.failed",
            extra={"skill_id": str(skill_id), "version_id": str(version_id), "error": str(exc)},
        )
        _raise(exc)
    return Response(status_code=204)


@public_router.get("/{skill_id}/versions/{version}/package")
async def download_skill_package_endpoint(
    skill_id: uuid.UUID,
    version: str,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> FileResponse:
    logger.info("download_skill_package.start", extra={"skill_id": str(skill_id), "version": version})
    item = await get_skill_version(db, skill_id, version)
    path = storage.get_object_path(item.object_key) if item is not None else None
    if path is None:
        logger.warning(
            "download_skill_package.failed",
            extra={"skill_id": str(skill_id), "version": version, "reason": "not_found"},
        )
        raise_problem(404, "SKILL_PACKAGE_NOT_FOUND", "Skill package not found")
    logger.info("download_skill_package.completed", extra={"skill_id": str(skill_id), "version": version})
    return FileResponse(
        cast(Path, path),
        media_type="application/zip",
        filename=f"{skill_id}-{version}.zip",
    )
