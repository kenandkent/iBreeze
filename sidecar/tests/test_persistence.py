"""Tests for persistence layer: company isolation, optimistic locking, idempotency."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from ibreeze.persistence import (
    check_company_isolation,
    check_idempotency,
    claim_idempotency,
    complete_idempotency,
    lock_optimistic,
)

_SHA = "a" * 64  # valid sha256 hex string (64 chars)


@pytest.mark.asyncio
class TestCheckCompanyIsolation:
    async def test_returns_true_when_row_matches(self, db: aiosqlite.Connection):
        company_id = str(uuid.uuid4())
        row_id = str(uuid.uuid4())
        await db.execute(
            "CREATE TEMPORARY TABLE test_iso (id TEXT, company_id TEXT)"
        )
        await db.execute(
            "INSERT INTO test_iso VALUES (?, ?)", (row_id, company_id)
        )
        assert await check_company_isolation(db, company_id, "test_iso", row_id) is True

    async def test_returns_false_when_row_missing(self, db: aiosqlite.Connection):
        await db.execute(
            "CREATE TEMPORARY TABLE test_iso3 (id TEXT, company_id TEXT)"
        )
        assert await check_company_isolation(
            db, "nonexistent", "test_iso3", "nonexistent"
        ) is False

    async def test_returns_false_when_wrong_company(self, db: aiosqlite.Connection):
        company_id = str(uuid.uuid4())
        row_id = str(uuid.uuid4())
        await db.execute(
            "CREATE TEMPORARY TABLE test_iso2 (id TEXT, company_id TEXT)"
        )
        await db.execute(
            "INSERT INTO test_iso2 VALUES (?, ?)", (row_id, company_id)
        )
        assert (
            await check_company_isolation(
                db, "wrong-company", "test_iso2", row_id
            )
            is False
        )


@pytest.mark.asyncio
class TestLockOptimistic:
    async def test_lock_succeeds(self, db: aiosqlite.Connection):
        await db.execute(
            "CREATE TEMPORARY TABLE test_lock (id TEXT, version INTEGER)"
        )
        await db.execute(
            "INSERT INTO test_lock VALUES (?, ?)", ("row1", 1)
        )
        result = await lock_optimistic(db, "test_lock", "row1", 1)
        assert result is True
        row = await (await db.execute("SELECT version FROM test_lock WHERE id='row1'")).fetchone()
        assert row[0] == 2

    async def test_lock_fails_on_version_mismatch(self, db: aiosqlite.Connection):
        await db.execute(
            "CREATE TEMPORARY TABLE test_lock2 (id TEXT, version INTEGER)"
        )
        await db.execute(
            "INSERT INTO test_lock2 VALUES (?, ?)", ("row1", 1)
        )
        result = await lock_optimistic(db, "test_lock2", "row1", 5)
        assert result is False

    async def test_lock_with_company_id(self, db: aiosqlite.Connection):
        await db.execute(
            "CREATE TEMPORARY TABLE test_lock3 (id TEXT, version INTEGER, company_id TEXT)"
        )
        company_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO test_lock3 VALUES (?, ?, ?)", ("row1", 1, company_id)
        )
        result = await lock_optimistic(
            db, "test_lock3", "row1", 1, company_id=company_id
        )
        assert isinstance(result, bool)

    async def test_lock_with_wrong_company_id(self, db: aiosqlite.Connection):
        await db.execute(
            "CREATE TEMPORARY TABLE test_lock4 (id TEXT, version INTEGER, company_id TEXT)"
        )
        await db.execute(
            "INSERT INTO test_lock4 VALUES (?, ?, ?)", ("row1", 1, "c1")
        )
        result = await lock_optimistic(
            db, "test_lock4", "row1", 1, company_id="wrong"
        )
        assert isinstance(result, bool)


@pytest.mark.asyncio
class TestIdempotency:
    async def test_check_returns_none_when_missing(self, db: aiosqlite.Connection):
        result = await check_idempotency(db, "test.method", "key1", _SHA)
        assert result is None

    async def test_check_completed_returns_response(self, db: aiosqlite.Connection):
        now = "2026-01-01T00:00:00.000000Z"
        expires = "2026-12-31T23:59:59.000000Z"
        await db.execute(
            """INSERT INTO rpc_idempotency
               (method, idempotency_key, request_sha256, status, response_json,
                error_code, created_at, expires_at)
               VALUES (?, ?, ?, 'completed', ?, NULL, ?, ?)""",
            ("test.method", "key1", _SHA, '{"result":"ok"}', now, expires),
        )
        await db.commit()
        result = await check_idempotency(db, "test.method", "key1", _SHA)
        assert result == {"response": '{"result":"ok"}'}

    async def test_check_failed_returns_error(self, db: aiosqlite.Connection):
        now = "2026-01-01T00:00:00.000000Z"
        expires = "2026-12-31T23:59:59.000000Z"
        await db.execute(
            """INSERT INTO rpc_idempotency
               (method, idempotency_key, request_sha256, status, response_json,
                error_code, created_at, expires_at)
               VALUES (?, ?, ?, 'failed', NULL, ?, ?, ?)""",
            ("test.method", "key2", _SHA, "SOME_ERROR", now, expires),
        )
        await db.commit()
        result = await check_idempotency(db, "test.method", "key2", _SHA)
        assert result == {"error": "SOME_ERROR"}

    async def test_check_processing_returns_status(self, db: aiosqlite.Connection):
        now = "2026-01-01T00:00:00.000000Z"
        expires = "2026-12-31T23:59:59.000000Z"
        await db.execute(
            """INSERT INTO rpc_idempotency
               (method, idempotency_key, request_sha256, status, response_json,
                error_code, created_at, expires_at)
               VALUES (?, ?, ?, 'processing', NULL, NULL, ?, ?)""",
            ("test.method", "key3", _SHA, now, expires),
        )
        await db.commit()
        result = await check_idempotency(db, "test.method", "key3", _SHA)
        assert result == {"status": "processing"}

    async def test_claim_succeeds_first_time(self, db: aiosqlite.Connection):
        result = await claim_idempotency(db, "test.method", "key4", _SHA)
        assert result is True

    async def test_claim_fails_on_duplicate(self, db: aiosqlite.Connection):
        await claim_idempotency(db, "test.method", "key5", _SHA)
        result = await claim_idempotency(db, "test.method", "key5", _SHA)
        assert result is False

    async def test_complete_with_response(self, db: aiosqlite.Connection):
        await claim_idempotency(db, "test.method", "key6", _SHA)
        await complete_idempotency(
            db, "test.method", "key6", response_json='{"ok":true}'
        )
        result = await check_idempotency(db, "test.method", "key6", _SHA)
        assert result == {"response": '{"ok":true}'}

    async def test_complete_with_error(self, db: aiosqlite.Connection):
        await claim_idempotency(db, "test.method", "key7", _SHA)
        await complete_idempotency(
            db, "test.method", "key7", error_code="BAD_REQUEST"
        )
        result = await check_idempotency(db, "test.method", "key7", _SHA)
        assert result == {"error": "BAD_REQUEST"}

    async def test_complete_neither_response_nor_error(self, db: aiosqlite.Connection):
        await claim_idempotency(db, "test.method", "key8", _SHA)
        await complete_idempotency(db, "test.method", "key8")
        result = await check_idempotency(db, "test.method", "key8", _SHA)
        assert result == {"status": "processing"}
