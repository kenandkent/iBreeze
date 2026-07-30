"""Tests for ibreeze.rpc.reverse_client module."""

from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.rpc.multiplexer import Multiplexer
from ibreeze.rpc.reverse_client import DEFAULT_RPC_TIMEOUT, ReverseClient


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
def client(multiplexer: Multiplexer, writer: AsyncMock) -> ReverseClient:
    return ReverseClient(
        multiplexer=multiplexer,
        writer=writer,
        session_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
    )


class TestReverseClient:
    async def test_call_sends_request_and_resolves(self, client: ReverseClient, multiplexer: Multiplexer):
        rpc_id = None
        original_register = multiplexer.register_pending

        def capture(rid, deadline):
            nonlocal rpc_id
            rpc_id = rid
            return original_register(rid, deadline)

        multiplexer.register_pending = capture

        async def resolve_soon():
            await asyncio.sleep(0.01)
            if rpc_id:
                multiplexer.resolve_pending(rpc_id, result={"status": "ok"})

        asyncio.create_task(resolve_soon())

        result = await client.call("test.method", {"param": "value"})
        assert result == {"status": "ok"}

    async def test_call_with_custom_deadline(self, client: ReverseClient, multiplexer: Multiplexer):
        rpc_id = None
        original_register = multiplexer.register_pending

        def capture(rid, deadline):
            nonlocal rpc_id
            rpc_id = rid
            return original_register(rid, deadline)

        multiplexer.register_pending = capture

        async def resolve_soon():
            await asyncio.sleep(0.01)
            if rpc_id:
                multiplexer.resolve_pending(rpc_id, result="custom_deadline_result")

        asyncio.create_task(resolve_soon())

        deadline = time.monotonic() + 60.0
        result = await client.call("method", {}, deadline_at=deadline)
        assert result == "custom_deadline_result"

    async def test_call_deadline_exceeded_before_response(self, client: ReverseClient, multiplexer: Multiplexer):
        from ibreeze.rpc.multiplexer import IpcDeadlineExceededError
        with patch("ibreeze.rpc.reverse_client.time.monotonic", side_effect=[0, 100]):
            multiplexer.register_pending("test", deadline=0.0)
            with pytest.raises(IpcDeadlineExceededError, match="deadline exceeded"):
                await client.call("test", {}, deadline_at=0.0)

    async def test_call_timeout_raises(self, client: ReverseClient, multiplexer: Multiplexer):
        from ibreeze.rpc.multiplexer import IpcDeadlineExceededError
        # Set a very short deadline so it times out quickly
        deadline = time.monotonic() + 0.01
        with patch("ibreeze.rpc.reverse_client.asyncio.wait_for", side_effect=TimeoutError):
            with pytest.raises(IpcDeadlineExceededError, match="deadline exceeded"):
                await client.call("slow_method", {}, deadline_at=deadline)

    async def test_notify_sends_frame(self, client: ReverseClient, writer: AsyncMock):
        await client.notify("notification.method", {"data": "test"})
        writer.write.assert_called_once()
        written_data = writer.write.call_args[0][0]
        import json
        import struct
        struct.unpack(">I", written_data[:4])[0]
        payload = json.loads(written_data[4:].decode("utf-8"))
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "notification.method"
        assert payload["params"] == {"data": "test"}

    async def test_stream_events_yields_events(self, client: ReverseClient, multiplexer: Multiplexer):
        req_id = uuid.uuid4()
        # Don't pre-register - stream_events will register itself
        # Instead, feed events into the queue after stream_events starts

        async def feed_after_registration():
            # Wait for stream_events to register the stream
            await asyncio.sleep(0.05)
            stream = multiplexer._streams.get(req_id)
            if stream is None:
                return
            stream.queue.put_nowait({"event": "started"})
            stream.queue.put_nowait({"event": "completed"})

        asyncio.create_task(feed_after_registration())

        events = []
        async for event in client.stream_events(req_id, timeout=2.0):
            events.append(event)
            if event.get("event") == "completed":
                break

        assert len(events) == 2
        assert events[0]["event"] == "started"
        assert events[1]["event"] == "completed"

    async def test_stream_events_timeout(self, client: ReverseClient, multiplexer: Multiplexer):
        req_id = uuid.uuid4()

        events = []
        async for event in client.stream_events(req_id, timeout=0.05):
            events.append(event)

        assert len(events) == 0
        assert multiplexer.stream_count == 0

    async def test_stream_events_breaks_on_failed(self, client: ReverseClient, multiplexer: Multiplexer):
        req_id = uuid.uuid4()

        async def feed_after_registration():
            await asyncio.sleep(0.05)
            stream = multiplexer._streams.get(req_id)
            if stream is None:
                return
            stream.queue.put_nowait({"event": "failed"})

        asyncio.create_task(feed_after_registration())

        events = []
        async for event in client.stream_events(req_id, timeout=2.0):
            events.append(event)

        assert len(events) == 1
        assert events[0]["event"] == "failed"

    async def test_stream_events_handles_exception(self, client: ReverseClient, multiplexer: Multiplexer):
        req_id = uuid.uuid4()

        async def feed_events():
            await asyncio.sleep(0.05)
            stream = multiplexer._streams.get(req_id)
            if stream is not None:
                raise RuntimeError("queue error")

        asyncio.create_task(feed_events())

        events = []
        async for event in client.stream_events(req_id, timeout=1.0):
            events.append(event)

        # Stream should be closed after exception
        assert multiplexer.stream_count == 0


class TestDefaultRpcTimeout:
    def test_default_timeout_value(self):
        assert DEFAULT_RPC_TIMEOUT == 30.0
