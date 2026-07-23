"""Append-only admin audit logging service."""
import uuid

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.audit_log import AuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    await db.execute(
        insert(AuditLog).values(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )
