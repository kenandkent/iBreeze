"""Canonical compatibility-rule management routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.models import CompatibilityRule
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
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.compatibility")

router = APIRouter(prefix="/admin/api/v1/compatibility-rules", tags=["compatibility"])
public_router = APIRouter(prefix="/api/v1/catalog", tags=["compatibility-public"])


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
    logger.info("create_rule.start", extra={"subject": body.subject, "dependency": body.dependency})
    result = RuleResponse.model_validate(await create_rule(db, body))
    logger.info("create_rule.completed", extra={"rule_id": str(result.id)})
    return result


@router.get("")
async def list_rules_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info("list_rules.start", extra={"limit": limit})
    items = {
        "items": [RuleResponse.model_validate(item) for item in await list_rules(db, limit)],
        "next_cursor": None,
    }
    logger.info("list_rules.completed", extra={"count": len(items["items"])})
    return items


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> RuleResponse:
    logger.info("get_rule.start", extra={"rule_id": str(rule_id)})
    item = await get_rule(db, rule_id)
    if item is None:
        logger.warning("get_rule.failed", extra={"rule_id": str(rule_id), "reason": "not_found"})
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
    logger.info("update_rule.start", extra={"rule_id": str(rule_id)})
    try:
        item = await update_rule(db, rule_id, body, _expected_version(if_match))
        logger.info("update_rule.completed", extra={"rule_id": str(rule_id)})
    except ValueError as exc:
        logger.error("update_rule.failed", extra={"rule_id": str(rule_id), "error": str(exc)})
        _raise(exc)
    return RuleResponse.model_validate(item)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule_endpoint(
    rule_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    logger.info("delete_rule.start", extra={"rule_id": str(rule_id)})
    try:
        await delete_rule(db, rule_id, _expected_version(if_match))
        logger.info("delete_rule.completed", extra={"rule_id": str(rule_id)})
    except ValueError as exc:
        logger.error("delete_rule.failed", extra={"rule_id": str(rule_id), "error": str(exc)})
        _raise(exc)
    return Response(status_code=204)


@router.post("/{rule_id}/validate", response_model=RuleResponse)
async def validate_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> RuleResponse:
    logger.info("validate_rule.start", extra={"rule_id": str(rule_id)})
    try:
        item = await validate_rule(db, rule_id)
        logger.info("validate_rule.completed", extra={"rule_id": str(rule_id)})
    except ValueError as exc:
        logger.error("validate_rule.failed", extra={"rule_id": str(rule_id), "error": str(exc)})
        _raise(exc)
    return RuleResponse.model_validate(item)


@public_router.get("/compatibility")
async def list_compatibility_rules_public(
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """列出所有已发布的兼容性规则（公开端点）"""
    logger.info("list_compatibility_rules_public")
    from sqlalchemy import select

    result = await db.execute(
        select(CompatibilityRule)
        .where(CompatibilityRule.status == "published")
        .order_by(CompatibilityRule.created_at.desc())
    )
    rules = result.scalars().all()

    logger.info("list_compatibility_rules_public_success", extra={"total": len(rules)})
    return {
        "data": [RuleResponse.model_validate(rule) for rule in rules],
        "meta": {"total": len(rules)},
    }
