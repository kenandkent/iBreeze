"""Knowledge generation tracking.

Ties SQLite embedding_generations records to LanceDB index state,
and exposes reconciliation helpers for the consolidation check.
"""

from __future__ import annotations

from typing import Any


async def get_active_generation(db: Any, company_id: str) -> dict[str, Any] | None:
    """Return the active embedding generation for a company."""
    cursor = await db.execute(
        """SELECT id, model_key, vector_dimension, source_event_sequence,
                  status, created_at, activated_at
           FROM embedding_generations
           WHERE company_id=? AND status='active'
           ORDER BY created_at DESC LIMIT 1""",
        (company_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def list_generations(db: Any, company_id: str) -> list[dict[str, Any]]:
    """Return all embedding generations for a company."""
    cursor = await db.execute(
        """SELECT id, model_key, vector_dimension, source_event_sequence,
                  status, created_at, activated_at
           FROM embedding_generations
           WHERE company_id=?
           ORDER BY created_at DESC""",
        (company_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def count_items_for_generation(db: Any, generation_id: str) -> int:
    """Count knowledge_items linked to a specific generation."""
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM knowledge_items WHERE embedding_generation_id=?",
        (generation_id,),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def count_lancedb_items(company_id: str) -> int:
    """Count rows in LanceDB for a company."""
    try:
        import lancedb  # type: ignore[import-untyped]

        db = lancedb.connect("~/.ibreeze/lancedb")
        try:
            table = db.open_table("knowledge_embeddings")
        except Exception:
            return 0
        results = table.search().where(f"company_id = '{company_id}'").limit(0).to_list()
        return len(results)
    except ImportError:
        return 0


async def count_lancedb_items_for_generation(generation_id: str) -> int:
    """Count rows in LanceDB for a specific generation."""
    try:
        import lancedb

        db = lancedb.connect("~/.ibreeze/lancedb")
        try:
            table = db.open_table("knowledge_embeddings")
        except Exception:
            return 0
        results = table.search().where(f"metadata LIKE '%{generation_id}%'").limit(0).to_list()
        return len(results)
    except ImportError:
        return 0
