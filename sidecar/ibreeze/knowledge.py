"""Company-scoped knowledge import, removal and permission-first retrieval."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ibreeze.schemas import KnowledgeItemCreate, KnowledgeItemResponse


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _one(cursor: Any) -> Any | None:
    return await cursor.fetchone()


def _response(row: Any) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        id=row["id"],
        company_id=row["company_id"],
        source_artifact_id=row["source_artifact_id"],
        source_message_event_id=row["source_message_event_id"],
        owner_employee_id=row["owner_employee_id"],
        department_id=row["department_id"],
        task_id=row["task_id"],
        visibility=row["visibility"],
        title=row["title"],
        content=row["content"],
        content_sha256=row["content_sha256"],
        embedding_generation_id=row["embedding_generation_id"],
        created_at=_datetime(row["created_at"]),
        version=row["version"],
    )


async def import_knowledge(
    db: Any,
    company_id: str,
    data: KnowledgeItemCreate,
) -> KnowledgeItemResponse:
    """Import one validated chunk and enqueue a generation rebuild atomically."""
    item_id = _id()
    event_id = _id()
    now = _now()
    content_sha = _sha256(data.content)
    await db.execute("BEGIN IMMEDIATE")
    try:
        company = await _one(
            await db.execute(
                "SELECT status FROM companies WHERE id=?",
                (company_id,),
            )
        )
        if company is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if company["status"] != "active":
            raise ValueError("COMPANY_ARCHIVED")

        duplicate = await _one(
            await db.execute(
                """SELECT id FROM knowledge_items
                   WHERE company_id=? AND content_sha256=? AND visibility=?
                   AND department_id IS ? AND task_id IS ?
                   AND owner_employee_id IS ?""",
                (
                    company_id,
                    content_sha,
                    data.visibility.value,
                    data.department_id,
                    data.task_id,
                    data.owner_employee_id,
                ),
            )
        )
        if duplicate is not None:
            raise ValueError("NAME_EXISTS")

        await db.execute(
            """INSERT INTO knowledge_items
               (id,company_id,source_artifact_id,source_message_event_id,
                owner_employee_id,department_id,task_id,visibility,title,
                content,content_sha256,embedding_generation_id,created_at,version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?,1)""",
            (
                item_id,
                company_id,
                data.source_artifact_id,
                data.source_message_event_id,
                data.owner_employee_id,
                data.department_id,
                data.task_id,
                data.visibility.value,
                data.title,
                data.content,
                content_sha,
                now,
            ),
        )
        payload = json.dumps(
            {
                "company_id": company_id,
                "knowledge_item_id": item_id,
                "source_artifact_id": data.source_artifact_id,
                "source_message_event_id": data.source_message_event_id,
                "visibility": data.visibility.value,
                "content_sha256": content_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        await db.execute(
            """INSERT INTO domain_events
               (event_id,company_id,aggregate_type,aggregate_id,
                aggregate_version,event_type,payload_json,trace_id,occurred_at)
               VALUES (?,?,'knowledge_item',?,1,'knowledge.imported',?,?,?)""",
            (event_id, company_id, item_id, payload, _id(), now),
        )
        await db.execute(
            """INSERT INTO outbox_events
               (id,domain_event_id,topic,payload_json,status,attempts,
                next_attempt_at,created_at)
               VALUES (?,?,'knowledge.index.requested',?,'pending',0,?,?)""",
            (_id(), event_id, payload, now, now),
        )
        await db.commit()
        return await get_knowledge(db, company_id, item_id)
    except Exception:
        await db.rollback()
        raise


async def get_knowledge(
    db: Any,
    company_id: str,
    item_id: str,
) -> KnowledgeItemResponse:
    row = await _one(
        await db.execute(
            "SELECT * FROM knowledge_items WHERE id=? AND company_id=?",
            (item_id, company_id),
        )
    )
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _response(row)


async def list_knowledge(
    db: Any,
    company_id: str,
    *,
    limit: int = 50,
    after: tuple[str, str] | None = None,
) -> list[KnowledgeItemResponse]:
    if after is None:
        cursor = await db.execute(
            """SELECT * FROM knowledge_items WHERE company_id=?
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (company_id, limit),
        )
    else:
        cursor = await db.execute(
            """SELECT * FROM knowledge_items WHERE company_id=?
               AND (created_at<? OR (created_at=? AND id<?))
               ORDER BY created_at DESC,id DESC LIMIT ?""",
            (company_id, after[0], after[0], after[1], limit),
        )
    return [_response(row) for row in await cursor.fetchall()]


async def remove_knowledge(
    db: Any,
    company_id: str,
    item_id: str,
) -> dict[str, object]:
    """Record the removal fact before deleting the source row."""
    await db.execute("BEGIN IMMEDIATE")
    try:
        row = await _one(
            await db.execute(
                "SELECT * FROM knowledge_items WHERE id=? AND company_id=?",
                (item_id, company_id),
            )
        )
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        event_id = _id()
        now = _now()
        next_version = int(row["version"]) + 1
        payload = json.dumps(
            {
                "company_id": company_id,
                "knowledge_item_id": item_id,
                "content_sha256": row["content_sha256"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        await db.execute(
            """INSERT INTO domain_events
               (event_id,company_id,aggregate_type,aggregate_id,
                aggregate_version,event_type,payload_json,trace_id,occurred_at)
               VALUES (?,?,'knowledge_item',?,?,'knowledge.removed',?,?,?)""",
            (
                event_id,
                company_id,
                item_id,
                next_version,
                payload,
                _id(),
                now,
            ),
        )
        await db.execute(
            """INSERT INTO outbox_events
               (id,domain_event_id,topic,payload_json,status,attempts,
                next_attempt_at,created_at)
               VALUES (?,?,'knowledge.index.requested',?,'pending',0,?,?)""",
            (_id(), event_id, payload, now, now),
        )
        await db.execute(
            "DELETE FROM knowledge_fts WHERE knowledge_id=? AND company_id=?",
            (item_id, company_id),
        )
        await db.execute(
            "DELETE FROM knowledge_items WHERE id=? AND company_id=?",
            (item_id, company_id),
        )
        await db.commit()
        return {"id": item_id, "removed": True}
    except Exception:
        await db.rollback()
        raise


async def permitted_knowledge_ids(
    db: Any,
    company_id: str,
    *,
    employee_id: str,
    department_id: str | None,
    company_task_id: str | None,
) -> list[str]:
    """Resolve the complete ACL candidate set before text/vector retrieval."""
    cursor = await db.execute(
        """SELECT id FROM knowledge_items
           WHERE company_id=? AND (
             visibility='company'
             OR (visibility='department' AND department_id IS ?)
             OR (visibility='task' AND task_id IS ?)
             OR (visibility='private' AND owner_employee_id=?)
           )
           ORDER BY id""",
        (company_id, department_id, company_task_id, employee_id),
    )
    return [str(row[0]) for row in await cursor.fetchall()]


async def search_knowledge(
    db: Any,
    company_id: str,
    query: str,
    *,
    run_id: str,
    employee_id: str,
    department_id: str | None,
    company_task_id: str | None,
    limit: int = 12,
) -> list[KnowledgeItemResponse]:
    """Search only the pre-authorized candidate set and write an access fact."""
    candidate_ids = await permitted_knowledge_ids(
        db,
        company_id,
        employee_id=employee_id,
        department_id=department_id,
        company_task_id=company_task_id,
    )
    selected: list[KnowledgeItemResponse] = []
    if candidate_ids:
        placeholders = ",".join("?" for _ in candidate_ids)
        cursor = await db.execute(
            f"""SELECT k.* FROM knowledge_fts f
                JOIN knowledge_items k
                  ON k.id=f.knowledge_id AND k.company_id=f.company_id
                WHERE f.company_id=? AND f.knowledge_id IN ({placeholders})
                  AND knowledge_fts MATCH ?
                ORDER BY bm25(knowledge_fts),k.id LIMIT ?""",
            (company_id, *candidate_ids, query, limit),
        )
        selected = [_response(row) for row in await cursor.fetchall()]

    scope = json.dumps(
        {
            "company_id": company_id,
            "department_id": department_id,
            "company_task_id": company_task_id,
            "employee_id": employee_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    selected_ids = [item.id for item in selected]
    context_hash = _sha256(
        json.dumps(selected_ids, separators=(",", ":"))
    )
    await db.execute(
        """INSERT INTO knowledge_access_logs
           (id,company_id,run_id,employee_id,query_sha256,
            visibility_scope_json,candidate_ids_json,selected_ids_json,
            context_pack_sha256,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            _id(),
            company_id,
            run_id,
            employee_id,
            _sha256(query),
            scope,
            json.dumps(candidate_ids, separators=(",", ":")),
            json.dumps(selected_ids, separators=(",", ":")),
            context_hash,
            _now(),
        ),
    )
    await db.commit()
    return selected
