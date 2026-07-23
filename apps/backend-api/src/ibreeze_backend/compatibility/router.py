"""Compatibility rule CRUD router."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.compatibility.schemas import (
    CompatibilityRuleCreate,
    CompatibilityRuleListResponse,
    CompatibilityRuleResponse,
    CompatibilityRuleUpdate,
    EvaluateRequest,
    EvaluateResponse,
)
from ibreeze_backend.compatibility.service import (
    create_rule,
    delete_rule,
    evaluate,
    get_rule,
    list_rules,
    update_rule,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User

router = APIRouter(
    prefix="/admin/api/v1/compatibility", tags=["compatibility"]
)


@router.post(
    "/rules",
    response_model=CompatibilityRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule_endpoint(
    body: CompatibilityRuleCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        rule = await create_rule(
            db,
            subject_type=body.subject_type,
            subject_version_range=body.subject_version_range,
            dependency_type=body.dependency_type,
            dependency_version_range=body.dependency_version_range,
            result=body.result,
            reason_code=body.reason_code,
            priority=body.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rule


@router.get("/rules", response_model=CompatibilityRuleListResponse)
async def list_rules_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    rules, total = await list_rules(db, skip=skip, limit=limit)
    return {"rules": rules, "total": total}


@router.get("/rules/{rule_id}", response_model=CompatibilityRuleResponse)
async def get_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    rule = await get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.patch(
    "/rules/{rule_id}", response_model=CompatibilityRuleResponse
)
async def update_rule_endpoint(
    rule_id: uuid.UUID,
    body: CompatibilityRuleUpdate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        rule = await update_rule(
            db,
            rule_id,
            subject_type=body.subject_type,
            subject_version_range=body.subject_version_range,
            dependency_type=body.dependency_type,
            dependency_version_range=body.dependency_version_range,
            result=body.result,
            reason_code=body.reason_code,
            priority=body.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rule


@router.delete(
    "/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_rule_endpoint(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        await delete_rule(db, rule_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_endpoint(
    body: EvaluateRequest,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    result, reason_code, rule_id = await evaluate(
        db,
        subject_type=body.subject_type,
        subject_version=body.subject_version,
        dependency_type=body.dependency_type,
        dependency_version=body.dependency_version,
    )
    return {
        "result": result,
        "reason_code": reason_code,
        "matched_rule_id": rule_id,
    }
