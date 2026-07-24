"""Company conversation intake and message projections."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from ibreeze.schemas import (
    ConversationResponse,
    MessageResponse,
    SubmitUserMessageRequest,
    SubmitUserMessageResponse,
)


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


def _conversation(row: Any) -> ConversationResponse:
    return ConversationResponse(
        id=row["id"],
        company_id=row["company_id"],
        conversation_type=row["conversation_type"],
        department_id=row["department_id"],
        status=row["status"],
        created_at=_dt(row["created_at"]),
    )


def _message(row: Any) -> MessageResponse:
    return MessageResponse(
        id=row["id"],
        company_id=row["company_id"],
        conversation_id=row["conversation_id"],
        task_id=row["task_id"],
        source_event_id=row["source_event_id"],
        sender_type=row["sender_type"],
        sender_employee_id=row["sender_employee_id"],
        message_type=row["message_type"],
        content=row["content"],
        artifact_refs_json=row["artifact_refs_json"],
        created_at=_dt(row["created_at"]),
    )


async def get_company_conversation(
    db: Any,
    company_id: str,
) -> ConversationResponse:
    cursor = await db.execute(
        """SELECT c.* FROM conversations c
           JOIN companies co ON co.company_conversation_id=c.id
           WHERE co.id=? AND c.company_id=?""",
        (company_id, company_id),
    )
    row = await _one(cursor)
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _conversation(row)


async def get_department_conversation(
    db: Any,
    company_id: str,
    department_id: str,
) -> ConversationResponse:
    cursor = await db.execute(
        """SELECT c.* FROM conversations c
           JOIN departments d ON d.department_conversation_id=c.id
           WHERE d.id=? AND d.company_id=? AND c.company_id=?""",
        (department_id, company_id, company_id),
    )
    row = await _one(cursor)
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _conversation(row)


async def list_messages(
    db: Any,
    company_id: str,
    conversation_id: str,
    *,
    limit: int = 50,
    after: tuple[str, str] | None = None,
) -> list[MessageResponse]:
    if after is None:
        cursor = await db.execute(
            """SELECT * FROM conversation_messages
               WHERE company_id=? AND conversation_id=?
               ORDER BY created_at ASC,id ASC LIMIT ?""",
            (company_id, conversation_id, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM conversation_messages
               WHERE company_id=? AND conversation_id=?
               AND (created_at > ? OR (created_at = ? AND id > ?))
               ORDER BY created_at ASC,id ASC LIMIT ?""",
            (
                company_id,
                conversation_id,
                after[0],
                after[0],
                after[1],
                limit,
            ),
        )
    return [_message(row) for row in await cursor.fetchall()]


async def submit_user_message(
    db: Any,
    data: SubmitUserMessageRequest,
) -> SubmitUserMessageResponse:
    if data.target_task_id and data.supersedes_task_id:
        raise ValueError("VALIDATION_FAILED")
    await db.execute("BEGIN IMMEDIATE")
    try:
        cursor = await db.execute(
            """SELECT co.status AS company_status, c.conversation_type,
                      c.department_id
               FROM companies co
               JOIN conversations c ON c.id=? AND c.company_id=co.id
               WHERE co.id=?""",
            (data.conversation_id, data.company_id),
        )
        scope = await _one(cursor)
        if scope is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if scope["company_status"] != "active":
            raise ValueError("COMPANY_ARCHIVED")
        if scope["conversation_type"] != "company" or scope["department_id"] is not None:
            raise ValueError("COMPANY_SCOPE_VIOLATION")

        now = _now()
        event_id = _id()
        message_id = _id()
        task_id = data.target_task_id or _id()
        if data.target_task_id:
            cursor = await db.execute(
                """SELECT * FROM company_tasks
                   WHERE id=? AND company_id=?""",
                (data.target_task_id, data.company_id),
            )
            task = await _one(cursor)
            if task is None or task["status"] not in {
                "awaiting_user_confirmation",
                "revision_requested",
            }:
                raise ValueError("STATE_TRANSITION_INVALID")
            task_version = task["version"] + 1
            task_status: Literal["draft", "revision_requested"] = (
                "revision_requested"
            )
            intake_mode: Literal[
                "new_task",
                "plan_revision",
                "superseding_task",
            ] = "plan_revision"
        else:
            task_version = 1
            task_status = "draft"
            intake_mode = "superseding_task" if data.supersedes_task_id else "new_task"
            if data.supersedes_task_id:
                cursor = await db.execute(
                    """SELECT created_at,status FROM company_tasks
                       WHERE id=? AND company_id=?""",
                    (data.supersedes_task_id, data.company_id),
                )
                prior = await _one(cursor)
                if prior is None or prior["status"] not in {
                    "cancelled",
                    "failed",
                }:
                    raise ValueError("STATE_TRANSITION_INVALID")

        payload = json.dumps(
            {
                "company_id": data.company_id,
                "aggregate_id": task_id,
                "aggregate_version": task_version,
                "conversation_id": data.conversation_id,
                "message_id": message_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        await db.execute(
            """INSERT INTO domain_events
               (event_id,company_id,aggregate_type,aggregate_id,
                aggregate_version,event_type,payload_json,trace_id,occurred_at)
               VALUES (?,?,'company_task',?,?, 'conversation.user_message_submitted',
                       ?,?,?)""",
            (
                event_id,
                data.company_id,
                task_id,
                task_version,
                payload,
                _id(),
                now,
            ),
        )

        if data.target_task_id:
            await db.execute(
                """UPDATE company_tasks
                   SET status='revision_requested',updated_at=?,version=?
                   WHERE id=? AND company_id=?""",
                (now, task_version, task_id, data.company_id),
            )
        else:
            title = data.content.strip().splitlines()[0][:200]
            await db.execute(
                """INSERT INTO company_tasks
                   (id,company_id,supersedes_task_id,company_conversation_id,
                    user_message_event_id,title,status,resume_state,
                    active_plan_id,created_at,updated_at,completed_at,version)
                   VALUES (?,?,?,?,?,?,'draft',NULL,NULL,?,?,NULL,1)""",
                (
                    task_id,
                    data.company_id,
                    data.supersedes_task_id,
                    data.conversation_id,
                    event_id,
                    title,
                    now,
                    now,
                ),
            )
        await db.execute(
            """INSERT INTO conversation_messages
               (id,company_id,conversation_id,task_id,source_event_id,
                sender_type,sender_employee_id,message_type,content,
                artifact_refs_json,created_at)
               VALUES (?,?,?,?,?,'user',NULL,'user_message',?,'[]',?)""",
            (
                message_id,
                data.company_id,
                data.conversation_id,
                task_id,
                event_id,
                data.content,
                now,
            ),
        )
        await db.execute(
            """INSERT INTO outbox_events
               (id,domain_event_id,topic,payload_json,status,attempts,
                next_attempt_at,created_at)
               VALUES (?,?,'company_task.analysis.requested',?,
                       'pending',0,?,?)""",
            (_id(), event_id, payload, now, now),
        )
        await db.commit()
        return SubmitUserMessageResponse(
            message_id=message_id,
            company_task_id=task_id,
            task_status=task_status,
            intake_mode=intake_mode,
            analysis_queued=True,
        )
    except Exception:
        await db.rollback()
        raise
