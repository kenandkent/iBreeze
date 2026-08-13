"""Tests for R09 knowledge reconciliation.

- KNOW-003: SQLite vs LanceDB count reconciliation
- KNOW-004: Active generation tracking
- KNOW-005: Generation item count tracking
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.knowledge.generation import (
    count_items_for_generation,
    get_active_generation,
    list_generations,
)
from ibreeze.knowledge.service import check_consolidation


def _make_mock_db():
    db = AsyncMock()
    cursor = AsyncMock()
    db.execute.return_value = cursor

    def configure_fetchone(table_data, default=None):
        async def fetchone():
            return table_data.get("row") if isinstance(table_data, dict) else table_data

        return fetchone

    return db


@pytest.fixture
def mock_db():
    db = AsyncMock()

    async def execute_side(sql, params=None):
        cursor = AsyncMock()
        if "as sqlite_count" in sql:
            cursor.fetchone.return_value = {"sqlite_count": 5}
        elif sql.startswith("SELECT id, model_key"):
            gen_row = {
                "id": "gen-1",
                "model_key": "text-embedding-ada-002",
                "vector_dimension": 384,
                "source_event_sequence": 42,
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "activated_at": "2024-01-01T01:00:00Z",
            }
            cursor.fetchone.return_value = gen_row
            cursor.fetchall.return_value = [gen_row]
        elif "as cnt" in sql:
            cursor.fetchone.return_value = {"cnt": 5}
        elif "embedding_generations" in sql:
            cursor.fetchall.return_value = [
                {
                    "id": "gen-1",
                    "model_key": "text-embedding-ada-002",
                    "vector_dimension": 384,
                    "source_event_sequence": 42,
                    "status": "active",
                    "created_at": "2024-01-01T00:00:00Z",
                    "activated_at": "2024-01-01T01:00:00Z",
                }
            ]
        else:
            cursor.fetchone.return_value = None
            cursor.fetchall.return_value = []
        return cursor

    db.execute.side_effect = execute_side
    return db


@pytest.mark.asyncio
class TestSqliteLanceDbReconciliation:
    """KNOW-003: SQLite vs LanceDB count reconciliation."""

    @patch("ibreeze.knowledge.service.count_lancedb_items")
    async def test_consolidation_returns_counts(self, mock_lance, mock_db):
        mock_lance.return_value = 5
        result = await check_consolidation(mock_db, "company-1")
        assert result["sqlite_count"] == 5
        assert result["lance_count"] == 5
        assert result["status"] == "consistent"

    @patch("ibreeze.knowledge.service.count_lancedb_items")
    async def test_consolidation_detects_mismatch(self, mock_lance, mock_db):
        mock_lance.return_value = 3
        result = await check_consolidation(mock_db, "company-1")
        assert result["status"] == "inconsistent"
        assert result["sqlite_count"] == 5
        assert result["lance_count"] == 3


@pytest.mark.asyncio
class TestActiveGenerationTracking:
    """KNOW-004: Active generation tracking."""

    async def test_get_active_generation(self, mock_db):
        gen = await get_active_generation(mock_db, "company-1")
        assert gen is not None
        assert gen["id"] == "gen-1"
        assert gen["model_key"] == "text-embedding-ada-002"
        assert gen["vector_dimension"] == 384

    async def test_get_active_generation_no_result(self):
        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = None
        db.execute.return_value = cursor
        gen = await get_active_generation(db, "company-none")
        assert gen is None

    async def test_list_generations(self, mock_db):
        gens = await list_generations(mock_db, "company-1")
        assert len(gens) >= 1


@pytest.mark.asyncio
class TestGenerationItemCount:
    """KNOW-005: Generation item count tracking."""

    async def test_count_items_for_generation(self, mock_db):
        count = await count_items_for_generation(mock_db, "gen-1")
        assert count == 5
