"""RRF hybrid search — BM25 (FTS5) + cosine similarity (LanceDB)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .embeddings import get_embedding_service
from .text_search import search_fts
from .vector_store import get_vector_store

RRF_K = 60  # Reciprocal Rank Fusion constant (J.7)


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def reciprocal_rank_fusion(
    result_lists: list[list[dict[str, Any]]],
    k: int = RRF_K,
) -> list[dict[str, Any]]:
    """Reciprocal Rank Fusion of multiple result lists.

    ``score += 1 / (k + rank)`` per J.7.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}

    for results in result_lists:
        for rank, item in enumerate(results, start=1):
            item_id = item.get("id", "")
            scores[item_id] = scores.get(item_id, 0) + 1.0 / (k + rank)
            if item_id not in items:
                items[item_id] = item

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    return [{**items[iid], "rrf_score": scores[iid]} for iid in sorted_ids]


async def hybrid_search(
    db: Any,
    company_id: str,
    query: str,
    *,
    candidate_ids: list[str] | None = None,
    generation_id: str | None = None,
    run_id: str | None = None,
    employee_id: str | None = None,
    department_id: str | None = None,
    company_task_id: str | None = None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Hybrid search combining BM25 (FTS5) and cosine similarity (LanceDB).

    Permission-first: *candidate_ids* is the pre-authorized ACL whitelist.
    Both FTS5 and LanceDB are filtered to the active generation and the
    candidate whitelist.  Results are fused with RRF and deduplicated.
    """
    # --- BM25 results via FTS5 ---
    bm25_limit = limit * 2  # J.7: top 50 from each branch, we use 2× as budget
    bm25_results = await search_fts(
        db,
        query,
        company_id,
        generation_id=generation_id,
        limit=bm25_limit,
    )

    # Filter to authorized candidates
    if candidate_ids is not None:
        candidate_set = set(candidate_ids)
        bm25_results = [r for r in bm25_results if r.get("id") in candidate_set]

    # --- Cosine similarity results via LanceDB ---
    embedding_service = get_embedding_service()
    query_embedding = embedding_service.embed_single(query)
    vector_store = get_vector_store()
    cosine_results = vector_store.search(
        company_id,
        query_embedding,
        limit=bm25_limit,
        generation_id=generation_id,
    )

    # Filter cosine results to authorized candidates
    if candidate_ids is not None:
        candidate_set = set(candidate_ids)
        cosine_results = [r for r in cosine_results if r.get("id") in candidate_set]

    # --- RRF fusion ---
    fused = reciprocal_rank_fusion([bm25_results, cosine_results])
    selected = fused[:limit]

    # --- Write knowledge_access_logs (J.7) ---
    if run_id and employee_id:
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
        candidate_order = [r.get("id", "") for r in bm25_results]
        selected_ids = [r.get("id", "") for r in selected]
        context_hash = _sha256(json.dumps(selected_ids, separators=(",", ":")))

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
                json.dumps(candidate_order, separators=(",", ":")),
                json.dumps(selected_ids, separators=(",", ":")),
                context_hash,
                _now(),
            ),
        )
    return selected
