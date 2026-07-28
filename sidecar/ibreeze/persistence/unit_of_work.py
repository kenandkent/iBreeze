from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

import aiosqlite

from ibreeze.events.outbox import OutboxWriter
from ibreeze.events.store import DomainEventStore
from ibreeze.persistence.idempotency import IdempotencyStore
from ibreeze.persistence.types import WriteSession


@dataclass
class CommandResult:
    response: Any
    events: Any = ()
    outbox: Any = ()


class UnitOfWork:
    def __init__(
        self,
        connection: aiosqlite.Connection,
        idempotency: IdempotencyStore | None = None,
        event_store: DomainEventStore | None = None,
        outbox: OutboxWriter | None = None,
    ) -> None:
        self._connection = connection
        self._idempotency = idempotency or IdempotencyStore()
        self._event_store = event_store or DomainEventStore()
        self._outbox = outbox or OutboxWriter()

    async def execute(
        self,
        idempotency_key: str | None,
        request_sha256: str,
        command: Callable[[WriteSession], Awaitable[CommandResult]],
        company_id: UUID | None = None,
        ttl_days: int = 30,
    ) -> Any:
        session = WriteSession(connection=self._connection, company_id=company_id)
        if idempotency_key:
            cached = await self._idempotency.lookup(session, idempotency_key, request_sha256)
            if cached is not None:
                return cached
        await self._connection.execute("BEGIN IMMEDIATE")
        try:
            if idempotency_key:
                claimed = await self._idempotency.claim(
                    session, idempotency_key, request_sha256,
                    ttl=timedelta(days=ttl_days),
                )
                if not claimed:
                    await self._connection.rollback()
                    raise RuntimeError("IDEMPOTENCY_CLAIM_FAILED")
            result = await command(session)
            await self._event_store.append_all(session, result.events)
            await self._outbox.enqueue_all(session, result.outbox)
            if idempotency_key:
                resp = result.response
                response_json = json.dumps(resp, default=str) if not isinstance(resp, str) else resp
                await self._idempotency.complete(session, idempotency_key, response_json=response_json)
            await self._connection.commit()
        except Exception:
            await self._connection.rollback()
            raise
        return result.response
