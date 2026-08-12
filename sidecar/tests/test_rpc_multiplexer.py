"""Tests for ibreeze.rpc.multiplexer module."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from ibreeze.rpc.multiplexer import (
    ActiveStream,
    IpcBackpressureError,
    IpcConnectionLostError,
    IpcError,
    MethodNotAllowedError,
    Multiplexer,
    PendingRequest,
)


@pytest.fixture
def mux() -> Multiplexer:
    return Multiplexer()


class TestMultiplexerProperties:
    def test_generation_starts_at_zero(self, mux: Multiplexer):
        assert mux.generation == 0

    def test_pending_count_starts_zero(self, mux: Multiplexer):
        assert mux.pending_count == 0

    def test_stream_count_starts_zero(self, mux: Multiplexer):
        assert mux.stream_count == 0


class TestPendingRequests:
    async def test_register_pending(self, mux: Multiplexer):
        future = mux.register_pending("rpc:1", deadline=100.0)
        assert mux.pending_count == 1
        assert isinstance(future, asyncio.Future)

    async def test_resolve_pending_with_result(self, mux: Multiplexer):
        future = mux.register_pending("rpc:1", deadline=100.0)
        mux.resolve_pending("rpc:1", result={"ok": True})
        assert future.result() == {"ok": True}
        assert mux.pending_count == 0

    async def test_resolve_pending_with_error(self, mux: Multiplexer):
        future = mux.register_pending("rpc:1", deadline=100.0)
        mux.resolve_pending("rpc:1", error="SOME_ERROR")
        with pytest.raises(IpcError, match="SOME_ERROR"):
            future.result()
        assert mux.pending_count == 0

    async def test_resolve_nonexistent_pending_is_noop(self, mux: Multiplexer):
        # Should not raise
        mux.resolve_pending("nonexistent")
        assert mux.pending_count == 0

    async def test_cancel_pending(self, mux: Multiplexer):
        future = mux.register_pending("rpc:1", deadline=100.0)
        mux.cancel_pending("rpc:1")
        with pytest.raises(IpcError, match="IPC_CONNECTION_LOST"):
            future.result()

    async def test_backpressure_error(self, mux: Multiplexer):
        from ibreeze.rpc.multiplexer import MAX_PENDING_PER_DIRECTION
        for i in range(MAX_PENDING_PER_DIRECTION):
            mux.register_pending(f"rpc:{i}", deadline=100.0)
        with pytest.raises(IpcBackpressureError, match="too many pending requests"):
            mux.register_pending("rpc:overflow", deadline=100.0)


class TestStreams:
    async def test_register_stream(self, mux: Multiplexer):
        req_id = uuid.uuid4()
        queue = mux.register_stream(req_id)
        assert mux.stream_count == 1
        assert isinstance(queue, asyncio.Queue)

    async def test_push_stream_frame(self, mux: Multiplexer):
        req_id = uuid.uuid4()
        queue = mux.register_stream(req_id)
        mux.push_stream_frame(req_id, {"event": "started"})
        assert queue.qsize() == 1
        assert queue.get_nowait() == {"event": "started"}

    async def test_push_stream_frame_not_found(self, mux: Multiplexer):
        with pytest.raises(IpcConnectionLostError, match="stream not found"):
            mux.push_stream_frame(uuid.uuid4(), {})

    async def test_push_stream_frame_buffer_full(self, mux: Multiplexer):
        from ibreeze.rpc.multiplexer import MAX_STREAM_BUFFER_FRAMES
        req_id = uuid.uuid4()
        queue = mux.register_stream(req_id)
        for i in range(MAX_STREAM_BUFFER_FRAMES):
            queue.put_nowait({"seq": i})
        with pytest.raises(IpcBackpressureError, match="stream buffer full"):
            mux.push_stream_frame(req_id, {"overflow": True})

    async def test_close_stream(self, mux: Multiplexer):
        req_id = uuid.uuid4()
        mux.register_stream(req_id)
        assert mux.stream_count == 1
        mux.close_stream(req_id)
        assert mux.stream_count == 0

    async def test_close_nonexistent_stream_is_noop(self, mux: Multiplexer):
        mux.close_stream(uuid.uuid4())
        assert mux.stream_count == 0

    async def test_close_all_streams(self, mux: Multiplexer):
        for _ in range(5):
            mux.register_stream(uuid.uuid4())
        assert mux.stream_count == 5
        mux.close_all_streams()
        assert mux.stream_count == 0

    async def test_stream_backpressure(self, mux: Multiplexer):
        from ibreeze.rpc.multiplexer import MAX_PENDING_PER_DIRECTION
        for i in range(MAX_PENDING_PER_DIRECTION):
            mux.register_stream(uuid.uuid4())
        with pytest.raises(IpcBackpressureError, match="too many streams"):
            mux.register_stream(uuid.uuid4())


class TestCancelAll:
    async def test_cancel_all_pending(self, mux: Multiplexer):
        f1 = mux.register_pending("rpc:1", deadline=100.0)
        f2 = mux.register_pending("rpc:2", deadline=100.0)
        mux.cancel_all()
        assert mux.pending_count == 0
        with pytest.raises(IpcError):
            f1.result()
        with pytest.raises(IpcError):
            f2.result()

    async def test_cancel_all_closes_streams(self, mux: Multiplexer):
        mux.register_stream(uuid.uuid4())
        mux.register_stream(uuid.uuid4())
        mux.cancel_all()
        assert mux.stream_count == 0

    async def test_cancel_all_with_custom_error(self, mux: Multiplexer):
        future = mux.register_pending("rpc:1", deadline=100.0)
        mux.cancel_all(error="CUSTOM_ERROR")
        with pytest.raises(IpcError, match="CUSTOM_ERROR"):
            future.result()


class TestBumpGeneration:
    async def test_bump_generation(self, mux: Multiplexer):
        assert mux.generation == 0
        gen = mux.bump_generation()
        assert gen == 1
        assert mux.generation == 1

    async def test_bump_generation_cancels_all(self, mux: Multiplexer):
        mux.register_pending("rpc:1", deadline=100.0)
        mux.register_stream(uuid.uuid4())
        mux.bump_generation()
        assert mux.pending_count == 0
        assert mux.stream_count == 0


class TestExceptionClasses:
    def test_ipc_error_hierarchy(self):
        assert issubclass(IpcBackpressureError, IpcError)
        assert issubclass(IpcConnectionLostError, IpcError)
        assert issubclass(MethodNotAllowedError, IpcError)
        assert issubclass(IpcError, Exception)


class TestDataclasses:
    @pytest.mark.asyncio
    async def test_pending_request_defaults(self):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        pr = PendingRequest(deadline=100.0, response_future=future)
        assert pr.deadline == 100.0
        assert pr.response_future is future
        assert isinstance(pr.cancel_event, asyncio.Event)

    def test_active_stream_defaults(self):
        stream = ActiveStream()
        assert stream.next_sequence == 1
        assert isinstance(stream.queue, asyncio.Queue)
        assert stream.queue.maxsize == 64
