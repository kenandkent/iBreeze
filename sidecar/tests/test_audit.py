"""Append-only audit tests."""

from __future__ import annotations

import json

import aiosqlite
import pytest

from ibreeze.audit import append_audit, list_audit
from ibreeze.schemas import AuditActorType, AuditOutcome


@pytest.mark.asyncio
async def test_audit_is_persistent_scoped_and_redacted(
    db: aiosqlite.Connection,
    uuid_value: str,
) -> None:
    audit = await append_audit(
        db,
        company_id=None,
        actor_type=AuditActorType.USER,
        actor_id="user",
        action="auth.login",
        resource_type="session",
        resource_id=None,
        outcome=AuditOutcome.SUCCESS,
        detail={
            "device": "desktop",
            "password": "never-store-this",
            "nested": {"token": "also-secret"},
        },
        trace_id=uuid_value,
    )
    detail = json.loads(audit.detail_json)
    assert detail["device"] == "desktop"
    assert detail["password"]["redacted"] is True
    assert "never-store-this" not in audit.detail_json
    assert detail["nested"]["token"]["redacted"] is True
    assert [row.id for row in await list_audit(db, company_id=None)] == [
        audit.id
    ]
    with pytest.raises(aiosqlite.IntegrityError):
        await db.execute(
            "UPDATE audit_logs SET action='tampered' WHERE id=?",
            (audit.id,),
        )
