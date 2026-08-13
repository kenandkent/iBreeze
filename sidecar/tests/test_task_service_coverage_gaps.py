"""Gap coverage for task/service.py reject_plan.

test_task_service_gaps.py already covers reject_plan success and
RESOURCE_NOT_FOUND.  The remaining uncovered branch is the
STATE_TRANSITION_INVALID raise when the task is not in
``awaiting_user_confirmation`` (service.py:214).
"""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.task.service import reject_plan


async def _ensure_company_and_task(db: aiosqlite.Connection, company_id: str, task_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Test', 'draft', ?, ?, 1)""",
            (task_id, company_id, conv_id, msg_event, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.mark.asyncio
class TestRejectPlanStateTransition:
    async def test_reject_wrong_state_raises(self, db) -> None:
        company_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _ensure_company_and_task(db, company_id, task_id)
        # The fixture created the task in 'draft'; reject_plan only accepts
        # 'awaiting_user_confirmation' and must fail loudly otherwise.
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await reject_plan(db, company_id, task_id, "e1", reason="no")
