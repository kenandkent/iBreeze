"""Canonical compatibility-rule management routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.schemas import RuleCreate, RuleResponse, RuleUpdate
from ibreeze_backend.compatibility.service import (
    create_rule,
    delete_rule,
    get_rule,
    list_rules,
    update_rule,
    validate_rule,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User

router = APIRouter(prefix="/admin/api/v1/compatibility-rules", tags=["compatibility"])


def _expected_version(value: str | None) -> int:
    if value is None:
        raise HTTPException(status_code=428, detail="IF_MATCH_REQUIRED")
    try:
        return int(value.strip('"'))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="IF_MATCH_INVALID") from exc


def _raise(exc: ValueError) -> None:
    code = str(exc)
    if code == "CATALOG_RESOURCE_NOT_FOUND":
        status_code = 404
    elif code in {"CATALOG_REVISION_IMMUTABLE", "OPTIMISTIC_LOCK_CONFLICT"}:
        status_code = 409
    else:
        status_code = 422
    raise HTTPException(status_code=status_code, detail=code) from exc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RuleResponse)
async def create_rule_endpoint(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> RuleResponse:
    return RuleResponse.model_validate(await create_rule(db, body))


@router.get("")
async def list_rules_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return {
        "items": [RuleResponse.model_validate(item) for item in await list_rules(db, limit)],
        "next_cursor": None,
    }


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> RuleResponse:
    item = await get_rule(db, rule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="CATALOG_RESOURCE_NOT_FOUND")
    return RuleResponse.model_validate(item)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule_endpoint(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> RuleResponse:
    try:
        item = await update_rule(db, rule_id, body, _expected_version(if_match))
    except ValueError as exc:
        _raise(exc)
    return RuleResponse.model_validate(item)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_endpoint(
    rule_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    try:
        await delete_rule(db, rule_id, _expected_version(if_match))
    except ValueError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.post("/{rule_id}/validate", response_model=RuleResponse)
async def validate_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> RuleResponse:
    try:
        item = await validate_rule(db, rule_id)
    except ValueError as exc:
        _raise(exc)
    return RuleResponse.model_validate(item)
