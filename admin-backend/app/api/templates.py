import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.auth.rbac import require_permission
from app.database import get_db
from app.models.admin import AdminUser
from app.models.template import EmployeeTemplate
from app.schemas.capability import TemplateCreate, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_dict(t: EmployeeTemplate) -> dict:
    return {
        "template_id": t.template_id,
        "company_id": t.company_id,
        "name": t.name,
        "role": t.role,
        "description": t.description,
        "provider_id": t.provider_id,
        "capability_id": t.capability_id,
        "model": t.model,
        "status": t.status,
        "version": t.version,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.get("")
async def list_templates(
    company_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(EmployeeTemplate)
    if company_id:
        q = q.where(EmployeeTemplate.company_id == company_id)
    if status:
        q = q.where(EmployeeTemplate.status == status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return [_to_dict(t) for t in result.scalars().all()]


@router.post("", status_code=201)
async def create_template(
    req: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    template_id = str(uuid.uuid4())
    now = _now()
    template = EmployeeTemplate(
        template_id=template_id,
        company_id=req.company_id,
        name=req.name,
        role=req.role,
        description=req.description,
        provider_id=req.provider_id,
        capability_id=req.capability_id,
        model=req.model,
        status="draft",
        version="1",
        created_at=now,
        updated_at=now,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return _to_dict(template)


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    result = await db.execute(
        select(EmployeeTemplate).where(EmployeeTemplate.template_id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_dict(template)


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    req: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(
        select(EmployeeTemplate).where(EmployeeTemplate.template_id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if req.name is not None:
        template.name = req.name
    if req.role is not None:
        template.role = req.role
    if req.description is not None:
        template.description = req.description
    if req.provider_id is not None:
        template.provider_id = req.provider_id
    if req.capability_id is not None:
        template.capability_id = req.capability_id
    if req.model is not None:
        template.model = req.model
    template.updated_at = _now()
    await db.commit()
    await db.refresh(template)
    return _to_dict(template)


@router.post("/{template_id}/activate")
async def activate_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(
        select(EmployeeTemplate).where(EmployeeTemplate.template_id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.status not in ("draft", "archived"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot activate from status {template.status}",
        )
    template.status = "active"
    template.updated_at = _now()
    await db.commit()
    await db.refresh(template)
    return _to_dict(template)


@router.post("/{template_id}/archive")
async def archive_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_permission("capabilities")),
):
    result = await db.execute(
        select(EmployeeTemplate).where(EmployeeTemplate.template_id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive from status {template.status}",
        )
    template.status = "archived"
    template.updated_at = _now()
    await db.commit()
    await db.refresh(template)
    return _to_dict(template)
