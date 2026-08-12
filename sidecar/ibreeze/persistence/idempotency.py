from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from ibreeze.persistence.types import WriteSession


class IdempotencyStore:
    default_ttl = timedelta(days=30)

    async def lookup(
        self,
        session: WriteSession,
        idempotency_key: str | None,
        request_sha256: str,
    ) -> Any | None:
        if idempotency_key is None:
            return None
        cursor = await session.connection.execute(
            "SELECT status, response_json, error_code, request_sha256 "
            "FROM idempotency WHERE idempotency_key=?",
            (idempotency_key,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        if row["request_sha256"] != request_sha256:
            raise RuntimeError("IDEMPOTENCY_CONFLICT")
        if row["status"] == "completed" and row["response_json"]:
            return {"response": row["response_json"]}
        if row["status"] == "failed":
            return {"error": row["error_code"]}
        if row["status"] == "processing":
            raise RuntimeError("IDEMPOTENCY_CONFLICT")
        return None

    async def claim(
        self,
        session: WriteSession,
        idempotency_key: str,
        request_sha256: str,
        ttl: timedelta | None = None,
    ) -> bool:
        if ttl is None:
            ttl = self.default_ttl
        now = datetime.now(UTC)
        expires_at = (now + ttl).strftime("%Y-%m-%dT%H:%M:%SZ")
        now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            await session.connection.execute(
                "INSERT INTO idempotency (idempotency_key, request_sha256, status, created_at, expires_at) "
                "VALUES (?, ?, 'processing', ?, ?)",
                (idempotency_key, request_sha256, now_str, expires_at),
            )
            return True
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                return False
            raise

    async def complete(
        self,
        session: WriteSession,
        idempotency_key: str,
        *,
        response_json: str | None = None,
        error_code: str | None = None,
    ) -> None:
        if response_json is not None:
            await session.connection.execute(
                "UPDATE idempotency SET status='completed', response_json=? WHERE idempotency_key=?",
                (response_json, idempotency_key),
            )
        elif error_code is not None:
            await session.connection.execute(
                "UPDATE idempotency SET status='failed', error_code=? WHERE idempotency_key=?",
                (error_code, idempotency_key),
            )
