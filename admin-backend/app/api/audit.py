from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.admin import AdminUser
from app.models.governance import AuditLog

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    company_id: str | None = None,
    audit_type: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(AuditLog)
    if company_id:
        q = q.where(AuditLog.company_id == company_id)
    if audit_type:
        q = q.where(AuditLog.audit_type == audit_type)
    q = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()
    return [
        {
            "log_id": l.log_id,
            "company_id": l.company_id,
            "audit_type": l.audit_type,
            "actor_id": l.actor_id,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "details": l.details,
            "trace_id": l.trace_id,
            "created_at": l.created_at,
        }
        for l in logs
    ]


@router.get("/interventions")
async def list_interventions(
    company_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    q = select(AuditLog).where(AuditLog.audit_type == "intervention")
    if company_id:
        q = q.where(AuditLog.company_id == company_id)
    q = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()
    return [
        {
            "log_id": l.log_id,
            "company_id": l.company_id,
            "actor_id": l.actor_id,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "details": l.details,
            "created_at": l.created_at,
        }
        for l in logs
    ]
