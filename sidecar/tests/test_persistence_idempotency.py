from __future__ import annotations

import sqlite3
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from ibreeze.persistence.idempotency import IdempotencyStore


@pytest.fixture
def session():
    s = AsyncMock()
    s.connection = AsyncMock()
    return s


@pytest.mark.asyncio
class TestIdempotencyStore:
    async def test_lookup_returns_none_when_no_key(self, session):
        store = IdempotencyStore()
        result = await store.lookup(session, None, "sha")
        assert result is None

    async def test_lookup_returns_none_when_no_row(self, session):
        cursor = AsyncMock()
        cursor.fetchone.return_value = None
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        result = await store.lookup(session, "key1", "sha")
        assert result is None

    async def test_lookup_returns_response_when_completed(self, session):
        cursor = AsyncMock()
        cursor.fetchone.return_value = {
            "status": "completed",
            "response_json": '{"ok": true}',
            "error_code": None,
            "request_sha256": "sha",
        }
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        result = await store.lookup(session, "key1", "sha")
        assert result == {"response": '{"ok": true}'}

    async def test_lookup_returns_error_when_failed(self, session):
        cursor = AsyncMock()
        cursor.fetchone.return_value = {
            "status": "failed",
            "response_json": None,
            "error_code": "BAD_REQUEST",
            "request_sha256": "sha",
        }
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        result = await store.lookup(session, "key1", "sha")
        assert result == {"error": "BAD_REQUEST"}

    async def test_lookup_raises_when_processing(self, session):
        cursor = AsyncMock()
        cursor.fetchone.return_value = {
            "status": "processing",
            "response_json": None,
            "error_code": None,
            "request_sha256": "sha",
        }
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        with pytest.raises(RuntimeError, match="IDEMPOTENCY_CONFLICT"):
            await store.lookup(session, "key1", "sha")

    async def test_claim_returns_true_on_success(self, session):
        cursor = AsyncMock()
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        result = await store.claim(session, "key1", "sha")
        assert result is True
        session.connection.execute.assert_called_once()

    async def test_claim_returns_false_on_duplicate(self, session):
        session.connection.execute.side_effect = sqlite3.IntegrityError("UNIQUE constraint failed: idempotency.idempotency_key")
        store = IdempotencyStore()
        result = await store.claim(session, "key1", "sha")
        assert result is False

    async def test_claim_with_custom_ttl(self, session):
        cursor = AsyncMock()
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        result = await store.claim(session, "key1", "sha", ttl=timedelta(hours=1))
        assert result is True

    async def test_complete_with_response(self, session):
        cursor = AsyncMock()
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        await store.complete(session, "key1", response_json='{"ok": true}')
        session.connection.execute.assert_called_once()

    async def test_complete_with_error(self, session):
        cursor = AsyncMock()
        session.connection.execute.return_value = cursor
        store = IdempotencyStore()
        await store.complete(session, "key1", error_code="BAD_REQUEST")
        session.connection.execute.assert_called_once()

    async def test_complete_neither(self, session):
        store = IdempotencyStore()
        await store.complete(session, "key1")
        session.connection.execute.assert_not_called()
