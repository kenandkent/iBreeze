import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.governance import ApprovalType, KnowledgeRule
from app.models.knowledge import BudgetPolicy
from app.schemas.governance import (
    ApprovalTypeCreate,
    ApprovalTypeUpdate,
    BudgetPolicyUpdate,
    KnowledgeRuleCreate,
    KnowledgeRuleUpdate,
)

router = APIRouter(prefix="/api/governance", tags=["governance"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_type_dict(t: ApprovalType) -> dict:
    return {
        "type_id": t.type_id,
        "company_id": t.company_id,
        "name": t.name,
        "description": t.description,
        "config": t.config,
        "version": t.version,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


def _to_budget_dict(b: BudgetPolicy) -> dict:
    return {
        "id": b.id,
        "company_id": b.company_id,
        "version": b.version,
        "config": b.config,
        "status": b.status,
        "created_at": b.created_at,
    }


# --- Approval Types ---

@router.get("/approval-types")
async def list_approval_types(
    company_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(ApprovalType)
    if company_id:
        q = q.where(ApprovalType.company_id == company_id)
    result = await db.execute(q)
    return [_to_type_dict(t) for t in result.scalars().all()]


@router.post("/approval-types", status_code=201)
async def create_approval_type(
    req: ApprovalTypeCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    type_id = str(uuid.uuid4())
    now = _now()
    at = ApprovalType(
        type_id=type_id,
        company_id=req.company_id,
        name=req.name,
        description=req.description,
        config=req.config or {},
        version="1",
        created_at=now,
        updated_at=now,
    )
    db.add(at)
    await db.commit()
    await db.refresh(at)
    return _to_type_dict(at)


@router.put("/approval-types/{type_id}")
async def update_approval_type(
    type_id: str,
    req: ApprovalTypeUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    result = await db.execute(select(ApprovalType).where(ApprovalType.type_id == type_id))
    at = result.scalar_one_or_none()
    if not at:
        raise HTTPException(status_code=404, detail="Approval type not found")
    if req.name is not None:
        at.name = req.name
    if req.description is not None:
        at.description = req.description
    if req.config is not None:
        at.config = req.config
    at.updated_at = _now()
    await db.commit()
    await db.refresh(at)
    return _to_type_dict(at)


@router.delete("/approval-types/{type_id}", status_code=204)
async def delete_approval_type(
    type_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    result = await db.execute(select(ApprovalType).where(ApprovalType.type_id == type_id))
    at = result.scalar_one_or_none()
    if not at:
        raise HTTPException(status_code=404, detail="Approval type not found")
    await db.delete(at)
    await db.commit()


# --- Approvals (stubs — actual approval records live in Sidecar) ---

@router.get("/approvals")
async def list_approvals(
    company_id: str | None = None,
    _user: AdminUser = Depends(get_current_user),
):
    return []


@router.get("/approvals/{approval_id}")
async def get_approval(
    approval_id: str,
    _user: AdminUser = Depends(get_current_user),
):
    raise HTTPException(status_code=404, detail="Approval not found (managed by Sidecar)")


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    _user: AdminUser = Depends(require_permission("governance")),
):
    raise HTTPException(status_code=404, detail="Approval not found (managed by Sidecar)")


@router.post("/approvals", status_code=201)
async def create_approval(
    _user: AdminUser = Depends(require_permission("governance")),
):
    raise HTTPException(status_code=501, detail="Approvals are managed by Sidecar RPC")


# --- Budget Policy ---

@router.get("/budget-policy")
async def get_budget_policy(
    company_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(BudgetPolicy).where(
            BudgetPolicy.company_id == company_id,
            BudgetPolicy.status == "active",
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Budget policy not found")
    return _to_budget_dict(policy)


@router.put("/budget-policy")
async def update_budget_policy(
    company_id: str,
    req: BudgetPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    result = await db.execute(
        select(BudgetPolicy).where(
            BudgetPolicy.company_id == company_id,
            BudgetPolicy.status == "active",
        )
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Budget policy not found")
    policy.config = req.config
    policy.version = policy.version + 1
    await db.commit()
    await db.refresh(policy)
    return _to_budget_dict(policy)


@router.get("/budget/{task_id}")
async def get_task_budget(
    task_id: str,
    _user: AdminUser = Depends(get_current_user),
):
    return {"task_id": task_id, "budget": None, "message": "Budget managed by Sidecar"}


# --- Knowledge Rules ---

def _to_rule_dict(r: KnowledgeRule) -> dict:
    return {
        "rule_id": r.rule_id,
        "company_id": r.company_id,
        "name": r.name,
        "description": r.description,
        "category": r.category,
        "action": r.action,
        "enabled": r.enabled,
        "config": r.config,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


@router.get("/knowledge-rules")
async def list_knowledge_rules(
    company_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(KnowledgeRule)
    if company_id:
        q = q.where(KnowledgeRule.company_id == company_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_rule_dict(r) for r in result.scalars().all()]


@router.post("/knowledge-rules", status_code=201)
async def create_knowledge_rule(
    req: KnowledgeRuleCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    rule_id = str(uuid.uuid4())
    now = _now()
    rule = KnowledgeRule(
        rule_id=rule_id,
        company_id=req.company_id,
        name=req.name,
        description=req.description,
        category=req.category,
        action=req.action,
        enabled=1,
        config=req.config or {},
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _to_rule_dict(rule)


@router.put("/knowledge-rules/{rule_id}")
async def update_knowledge_rule(
    rule_id: str,
    req: KnowledgeRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    result = await db.execute(select(KnowledgeRule).where(KnowledgeRule.rule_id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Knowledge rule not found")
    if req.name is not None:
        rule.name = req.name
    if req.description is not None:
        rule.description = req.description
    if req.category is not None:
        rule.category = req.category
    if req.action is not None:
        rule.action = req.action
    if req.enabled is not None:
        rule.enabled = req.enabled
    if req.config is not None:
        rule.config = req.config
    rule.updated_at = _now()
    await db.commit()
    await db.refresh(rule)
    return _to_rule_dict(rule)


@router.delete("/knowledge-rules/{rule_id}", status_code=204)
async def delete_knowledge_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("governance")),
):
    result = await db.execute(select(KnowledgeRule).where(KnowledgeRule.rule_id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Knowledge rule not found")
    await db.delete(rule)
    await db.commit()
