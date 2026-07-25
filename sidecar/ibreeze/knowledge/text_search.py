"""FTS5 full-text search over knowledge_items via knowledge_fts."""

from __future__ import annotations

from typing import Any


async def search_fts(
    db: Any,
    query: str,
    company_id: str,
    *,
    generation_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search knowledge items using FTS5 BM25 ranking."""
    conditions = [
        "fts.company_id = ?",
        "fts.generation_id IS NOT NULL",
        "knowledge_fts MATCH ?",
    ]
    params: list[Any] = [company_id, query]
    if generation_id is not None:
        conditions.append("fts.generation_id = ?")
        params.append(generation_id)
    params.append(limit)

    where = " AND ".join(conditions)
    cursor = await db.execute(
        f"""
        SELECT ki.id, ki.title, ki.content, ki.source_artifact_id,
               ki.source_message_event_id, ki.owner_employee_id,
               ki.department_id, ki.task_id, ki.visibility,
               ki.content_sha256, ki.created_at, ki.version,
               rank AS bm25_score
        FROM knowledge_fts fts
        JOIN knowledge_items ki ON ki.id = fts.knowledge_id
          AND ki.company_id = fts.company_id
        WHERE {where}
        ORDER BY bm25(knowledge_fts)
        LIMIT ?
        """,
        tuple(params),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows] if rows else []
