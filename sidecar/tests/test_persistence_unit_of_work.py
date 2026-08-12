from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ibreeze.persistence.types import WriteSession
from ibreeze.persistence.unit_of_work import CommandResult, UnitOfWork


@pytest.mark.asyncio
class TestUnitOfWork:
    async def test_execute_without_idempotency_key(self):
        conn = AsyncMock()
        conn.in_transaction = True

        async def fake_command(session: WriteSession) -> CommandResult:
            return CommandResult(response={"ok": True})

        uow = UnitOfWork(connection=conn)
        result = await uow.execute(None, "sha", fake_command)
        assert result == {"ok": True}
        conn.execute.assert_not_called()
        conn.commit.assert_not_called()

    async def test_execute_with_idempotency_key_hit(self):
        conn = AsyncMock()
        conn.in_transaction = True

        async def fake_command(session: WriteSession) -> CommandResult:
            return CommandResult(response={"ok": True})

        uow = UnitOfWork(connection=conn)
        uow._idempotency = AsyncMock()
        uow._idempotency.lookup.return_value = {"cached": True}

        result = await uow.execute("key1", "sha", fake_command)
        assert result == {"cached": True}
        conn.execute.assert_not_called()

    async def test_execute_idempotency_miss(self):
        conn = AsyncMock()
        conn.in_transaction = True

        async def fake_command(session: WriteSession) -> CommandResult:
            return CommandResult(response={"ok": True})

        uow = UnitOfWork(connection=conn)
        uow._idempotency = AsyncMock()
        uow._idempotency.lookup.return_value = None
        uow._idempotency.claim.return_value = True

        result = await uow.execute("key1", "sha", fake_command)
        assert result == {"ok": True}
        uow._idempotency.claim.assert_awaited_once()
        uow._idempotency.complete.assert_awaited_once()
        conn.commit.assert_not_called()

    async def test_execute_idempotency_claim_fails(self):
        conn = AsyncMock()
        conn.in_transaction = True

        async def fake_command(session: WriteSession) -> CommandResult:
            return CommandResult(response={"ok": True})

        uow = UnitOfWork(connection=conn)
        uow._idempotency = AsyncMock()
        uow._idempotency.lookup.return_value = None
        uow._idempotency.claim.return_value = False

        with pytest.raises(RuntimeError, match="IDEMPOTENCY_CLAIM_FAILED"):
            await uow.execute("key1", "sha", fake_command)
        conn.rollback.assert_not_awaited()

    async def test_execute_rollback_on_error(self):
        conn = AsyncMock()
        conn.in_transaction = True

        async def fake_command(session: WriteSession) -> CommandResult:
            raise ValueError("something went wrong")

        uow = UnitOfWork(connection=conn)
        with pytest.raises(ValueError, match="something went wrong"):
            await uow.execute(None, "sha", fake_command)
        conn.rollback.assert_not_called()

    async def test_execute_with_events_and_outbox(self):
        conn = AsyncMock()
        conn.in_transaction = True
        uow = UnitOfWork(connection=conn)
        uow._event_store = AsyncMock()
        uow._outbox = AsyncMock()

        async def fake_command(session: WriteSession) -> CommandResult:
            return CommandResult(response="done", events=(1, 2), outbox=(3, 4))

        result = await uow.execute(None, "sha", fake_command)
        assert result == "done"
        uow._event_store.append_all.assert_awaited_once()
        uow._outbox.enqueue_all.assert_awaited_once()

    async def test_default_dependencies_created(self):
        conn = AsyncMock()
        uow = UnitOfWork(connection=conn)
        assert uow._idempotency is not None
        assert uow._event_store is not None
        assert uow._outbox is not None
