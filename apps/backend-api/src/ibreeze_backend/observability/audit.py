"""Append-only admin audit logging service – aligned with design doc G.7."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.models.audit_log import AdminAuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    request_id: uuid.UUID,
    outcome: str,
    before_json: dict | None = None,
    after_json: dict | None = None,
    error_code: str | None = None,
    ip_address: str | None = None,
) -> None:
    await db.execute(
        insert(AdminAuditLog).values(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            outcome=outcome,
            before_json=before_json,
            after_json=after_json,
            error_code=error_code,
            ip_address=ip_address,
            created_at=datetime.now(UTC).isoformat(),
        )
    )
