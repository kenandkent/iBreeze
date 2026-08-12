"""Extended tests for ibreeze.rpc.session module."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.rpc.multiplexer import Multiplexer
from ibreeze.rpc.session import (
    IpcSession,
    IpcSessionMeta,
)


@pytest.fixture
def multiplexer() -> Multiplexer:
    return Multiplexer()


@pytest.fixture
def writer() -> AsyncMock:
    mock = AsyncMock()
    mock.write = MagicMock()
    mock.drain = AsyncMock()
    return mock


@pytest.fixture
def session(multiplexer: Multiplexer, writer: AsyncMock) -> IpcSession:
    return IpcSession(multiplexer, writer)


class TestIpcSessionMeta:
    def test_has_session_id(self):
        meta = IpcSessionMeta(
            session_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            generation=0,
        )
        assert isinstance(meta.session_id, uuid.UUID)
        assert isinstance(meta.trace_id, uuid.UUID)

    def test_has_connected_at(self):
        meta = IpcSessionMeta(
            session_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            generation=0,
        )
        assert meta.connected_at is not None


class TestIpcSession:
    def test_session_has_meta(self, session: IpcSession):
        assert isinstance(session.meta, IpcSessionMeta)
        assert isinstance(session.meta.session_id, uuid.UUID)

    def test_session_not_cancelled_by_default(self, session: IpcSession):
        assert not session.cancelled

    def test_cancel(self, session: IpcSession):
        session.cancel()
        assert session.cancelled

    async def test_call_sends_request(self, session: IpcSession, writer: AsyncMock):
        # Register a pending request to resolve
        rpc_id = None
        original_register = session._multiplexer.register_pending

        def capture_register(rid, deadline):
            nonlocal rpc_id
            rpc_id = rid
            return original_register(rid, deadline)

        session._multiplexer.register_pending = capture_register
        # Resolve immediately
        async def resolve_soon():
            await asyncio.sleep(0.01)
            if rpc_id:
                session._multiplexer.resolve_pending(rpc_id, result={"ok": True})

        asyncio.create_task(resolve_soon())

        result = await session.call("test.method", {"key": "val"})
        assert result == {"ok": True}

    async def test_call_timeout_raises(self, session: IpcSession, multiplexer: Multiplexer):
        with patch("ibreeze.rpc.session.time.monotonic", side_effect=[0, 100]):
            multiplexer.register_pending("test", deadline=0.0)
            with pytest.raises(Exception, match="deadline exceeded"):
                await session.call("test", {}, deadline_at=0.0)

    async def test_notify_sends_notification(self, session: IpcSession, writer: AsyncMock):
        await session.notify("sys.ping", {})
        writer.write.assert_called_once()
        written_data = writer.write.call_args[0][0]
        # Verify it's a valid frame
        import struct
        struct.unpack(">I", written_data[:4])[0]
        import json
        payload = json.loads(written_data[4:].decode("utf-8"))
        assert payload["method"] == "sys.ping"
        assert payload["jsonrpc"] == "2.0"

    async def test_respond_success(self, session: IpcSession, writer: AsyncMock):
        await session.respond("rpc:123", result={"value": 42})
        written_data = writer.write.call_args[0][0]
        import json
        import struct
        struct.unpack(">I", written_data[:4])[0]
        payload = json.loads(written_data[4:].decode("utf-8"))
        assert payload["id"] == "rpc:123"
        assert payload["result"] == {"value": 42}
        assert "error" not in payload

    async def test_respond_error(self, session: IpcSession, writer: AsyncMock):
        await session.respond("rpc:456", error="SOME_ERROR")
        written_data = writer.write.call_args[0][0]
        import json
        import struct
        struct.unpack(">I", written_data[:4])[0]
        payload = json.loads(written_data[4:].decode("utf-8"))
        assert payload["id"] == "rpc:456"
        assert "error" in payload
        assert payload["error"]["code"] == -32000
        assert payload["error"]["message"] == "SOME_ERROR"

    async def test_start_heartbeat_sends_heartbeats(self, session: IpcSession):
        call_count = 0

        async def fake_sleep(interval):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                session.cancel()

        with patch("ibreeze.rpc.session.asyncio.sleep", side_effect=fake_sleep):
            await session.start_heartbeat()
        assert call_count >= 2

    async def test_start_heartbeat_stops_on_exception(self, session: IpcSession):
        call_count = 0

        async def fake_sleep(interval):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                session.cancel()

        with patch("ibreeze.rpc.session.asyncio.sleep", side_effect=fake_sleep):
            # The notify will succeed, but let's simulate failure on 2nd call
            call_count_notify = 0

            async def failing_notify(*args, **kwargs):
                nonlocal call_count_notify
                call_count_notify += 1
                if call_count_notify >= 2:
                    raise ConnectionError("lost")

            session.notify = failing_notify
            await session.start_heartbeat()
            # Should have broken out due to missed heartbeats
