"""Admin audit log query router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.audit_log import AdminAuditLog
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.observability.router")

router = APIRouter(prefix="/admin/api/v1", tags=["admin-audit"])


@router.get("/audit-logs")
async def list_audit_logs(
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> dict:
    """列出审计日志（带过滤条件）"""
    logger.info(
        "list_audit_logs",
        extra={"actor_id": actor_id, "action": action, "resource_type": resource_type},
    )

    conditions = []
    if actor_id:
        conditions.append(AdminAuditLog.actor_user_id == actor_id)
    if action:
        conditions.append(AdminAuditLog.action == action)
    if resource_type:
        conditions.append(AdminAuditLog.resource_type == resource_type)

    query = select(AdminAuditLog)
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    logger.info("list_audit_logs_success", extra={"total": len(logs)})
    return {
        "data": [
            {
                "id": str(log.id),
                "actor_user_id": str(log.actor_user_id) if log.actor_user_id else None,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "outcome": log.outcome,
                "ip_address": log.ip_address,
                "created_at": log.created_at,
            }
            for log in logs
        ],
        "meta": {"total": len(logs), "offset": offset, "limit": limit},
    }
