from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.backend import Backend, CompanyBackendDefault
from app.models.capability import (
    Capability,
    CapabilityVersion,
    PromptAsset,
    PromptAssetVersion,
    Skill,
    SkillBinding,
    SkillVersion,
)
from app.models.knowledge import (
    BudgetPolicy,
    KnowledgePolicy,
    NotificationPolicy,
    SecurityPolicy,
    WorkspacePolicy,
)
from app.models.provider import (
    Provider,
    ProviderPricingVersion,
    ProviderTierMapping,
)
from app.models.template import EmployeeTemplate

router = APIRouter(prefix="/api/sync", tags=["sync"])

SYNC_TABLES = [
    (Capability, "capabilities"),
    (CapabilityVersion, "capability_versions"),
    (Skill, "skills"),
    (SkillVersion, "skill_versions"),
    (SkillBinding, "skill_bindings"),
    (PromptAsset, "prompt_assets"),
    (PromptAssetVersion, "prompt_asset_versions"),
    (EmployeeTemplate, "employee_templates"),
    (KnowledgePolicy, "knowledge_policies"),
    (SecurityPolicy, "security_policies"),
    (WorkspacePolicy, "workspace_policies"),
    (NotificationPolicy, "notification_policies"),
    (BudgetPolicy, "budget_policies"),
    (Backend, "backends"),
    (CompanyBackendDefault, "company_backend_defaults"),
    (Provider, "providers"),
    (ProviderPricingVersion, "provider_pricing_versions"),
    (ProviderTierMapping, "provider_tier_mappings"),
]


def _row_to_dict(row) -> dict:
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        d[col.name] = val
    return d


@router.get("/config")
async def sync_config(
    company_id: str,
    since: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id is required")

    data = {"timestamp": datetime.now(timezone.utc).isoformat()}

    for model, key in SYNC_TABLES:
        q = select(model)
        company_col = getattr(model, "company_id", None)
        if company_col is not None:
            q = q.where(company_col == company_id)
        if since and hasattr(model, "updated_at"):
            q = q.where(model.updated_at > since)
        result = await db.execute(q)
        rows = result.scalars().all()
        data[key] = [_row_to_dict(r) for r in rows]

    return data
