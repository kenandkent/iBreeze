import asyncio
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

MAX_PENDING_PER_DIRECTION = 256
MAX_STREAM_BUFFER_FRAMES = 64
SEND_TIMEOUT = 5.0


class IpcError(Exception):
    pass


class IpcBackpressureError(IpcError):
    pass


class IpcConnectionLostError(IpcError):
    pass


class IpcDeadlineExceededError(IpcError):
    pass


class MethodNotAllowedError(IpcError):
    pass


@dataclass
class PendingRequest:
    deadline: float
    response_future: asyncio.Future[Any]
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class ActiveStream:
    next_sequence: int = 1
    queue: asyncio.Queue[Any] = field(default_factory=lambda: asyncio.Queue(maxsize=MAX_STREAM_BUFFER_FRAMES))


class Multiplexer:
    def __init__(self) -> None:
        self._generation: int = 0
        self._pending: dict[str, PendingRequest] = OrderedDict()
        self._streams: dict[uuid.UUID, ActiveStream] = {}
        self._writer: asyncio.Queue[tuple[bytes, asyncio.Future[Any]]] = asyncio.Queue()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def stream_count(self) -> int:
        return len(self._streams)

    def register_pending(
        self,
        rpc_id: str,
        deadline: float,
    ) -> asyncio.Future[Any]:
        if len(self._pending) >= MAX_PENDING_PER_DIRECTION:
            raise IpcBackpressureError("too many pending requests")
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending[rpc_id] = PendingRequest(
            deadline=deadline,
            response_future=future,
        )
        return future

    def resolve_pending(self, rpc_id: str, result: Any = None, error: str | None = None) -> None:
        request = self._pending.pop(rpc_id, None)
        if request is None:
            return
        if not request.response_future.done():
            if error:
                request.response_future.set_exception(IpcError(error))
            else:
                request.response_future.set_result(result)

    def cancel_pending(self, rpc_id: str) -> None:
        self.resolve_pending(rpc_id, error="IPC_CONNECTION_LOST")

    def register_stream(self, request_id: uuid.UUID) -> asyncio.Queue[Any]:
        if len(self._streams) >= MAX_PENDING_PER_DIRECTION:
            raise IpcBackpressureError("too many streams")
        stream = ActiveStream()
        self._streams[request_id] = stream
        return stream.queue

    def push_stream_frame(self, request_id: uuid.UUID, value: Any) -> None:
        stream = self._streams.get(request_id)
        if stream is None:
            raise IpcConnectionLostError("stream not found")
        try:
            stream.queue.put_nowait(value)
        except asyncio.QueueFull:
            raise IpcBackpressureError("stream buffer full")

    def close_stream(self, request_id: uuid.UUID) -> None:
        self._streams.pop(request_id, None)

    def close_all_streams(self) -> None:
        self._streams.clear()

    def cancel_all(self, error: str = "IPC_CONNECTION_LOST") -> None:
        for rpc_id in list(self._pending.keys()):
            self.resolve_pending(rpc_id, error=error)
        self.close_all_streams()

    def bump_generation(self) -> int:
        self._generation += 1
        self.cancel_all()
        return self._generation
