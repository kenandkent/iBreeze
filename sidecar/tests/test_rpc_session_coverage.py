"""Coverage tests for ibreeze/rpc/session.py (uncovered branches)."""

from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.rpc.multiplexer import Multiplexer
from ibreeze.rpc.session import (
    IpcDeadlineExceeded,
    IpcSession,
)


@pytest.fixture
def multiplexer() -> Multiplexer:
    return Multiplexer()


@pytest.fixture
def writer() -> AsyncMock:
    mock = AsyncMock()
    mock.write = MagicMock()
    mock.drain = AsyncMock()
    mock.close = MagicMock()
    mock.wait_closed = AsyncMock()
    return mock


@pytest.fixture
def session(multiplexer: Multiplexer, writer: AsyncMock) -> IpcSession:
    return IpcSession(multiplexer, writer)


class TestClose:
    @pytest.mark.asyncio
    async def test_close_cancels_and_closes_writer(self, session, writer):
        await session.close()
        assert session.cancelled
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_swallows_wait_closed_error(self, multiplexer):
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock(side_effect=ConnectionError("reset"))
        session = IpcSession(multiplexer, writer)
        await session.close()  # must not raise
        assert session.cancelled

    @pytest.mark.asyncio
    async def test_close_swallows_oserror(self, multiplexer):
        writer = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock(side_effect=OSError("io"))
        session = IpcSession(multiplexer, writer)
        await session.close()  # must not raise


class TestBindSessionId:
    def test_bind_updates_meta(self, session):
        sid = uuid.uuid4()
        session.bind_session_id(sid)
        assert session.meta.session_id == sid


class TestResolveResponse:
    def test_non_string_id_ignored(self, session):
        session._multiplexer.resolve_pending = MagicMock()
        session.resolve_response({"id": 123})
        session._multiplexer.resolve_pending.assert_not_called()

    def test_missing_id_ignored(self, session):
        session._multiplexer.resolve_pending = MagicMock()
        session.resolve_response({"result": {}})
        session._multiplexer.resolve_pending.assert_not_called()

    def test_error_dict_with_message(self, session):
        session._multiplexer.resolve_pending = MagicMock()
        session.resolve_response({"id": "rpc:1", "error": {"message": "boom"}})
        session._multiplexer.resolve_pending.assert_called_once_with("rpc:1", error="boom")

    def test_error_non_dict_uses_default(self, session):
        session._multiplexer.resolve_pending = MagicMock()
        session.resolve_response({"id": "rpc:1", "error": "oops"})
        session._multiplexer.resolve_pending.assert_called_once_with("rpc:1", error="IPC_ERROR")

    def test_result_resolved(self, session):
        session._multiplexer.resolve_pending = MagicMock()
        session.resolve_response({"id": "rpc:1", "result": {"ok": True}})
        session._multiplexer.resolve_pending.assert_called_once_with("rpc:1", result={"ok": True})


class TestCallBranches:
    @pytest.mark.asyncio
    async def test_write_failure_cancels_pending(self, session):
        with patch(
            "ibreeze.rpc.session.write_frame",
            new=AsyncMock(side_effect=ConnectionError("broken pipe")),
        ):
            with pytest.raises(ConnectionError):
                await session.call("method", {})
        assert session._multiplexer.pending_count == 0

    @pytest.mark.asyncio
    async def test_timeout_cancels_pending(self, session):
        deadline_at = time.monotonic() + 0.2
        with pytest.raises(IpcDeadlineExceeded, match="deadline exceeded"):
            await session.call("method", {}, deadline_at=deadline_at)
        assert session._multiplexer.pending_count == 0


class TestStartHeartbeat:
    @pytest.mark.asyncio
    async def test_exits_immediately_when_cancelled(self, session):
        session.cancel()
        await session.start_heartbeat()  # while condition is False -> exit

    @pytest.mark.asyncio
    async def test_missed_heartbeats_cancel_session(self, session):
        with (
            patch("ibreeze.rpc.session.asyncio.sleep", new=AsyncMock()),
            patch.object(session, "notify", new=AsyncMock(side_effect=ConnectionError("lost"))),
        ):
            await session.start_heartbeat()
        assert session.cancelled
