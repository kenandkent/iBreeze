"""流式通知协议：ring buffer + StreamManager。"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from typing import Optional

_TTL = timedelta(minutes=5)
_MAX_BUFFER = 1000


class StreamBuffer:
    """单个流的 ring buffer，最多保留 1000 条消息，5 分钟 TTL。"""

    def __init__(self, aggregate_type: str, aggregate_id: str) -> None:
        self.stream_id = str(uuid.uuid4())
        self.aggregate_type = aggregate_type
        self.aggregate_id = aggregate_id
        self._messages: OrderedDict[int, dict] = OrderedDict()
        self._next_seq = 1
        self.created_at = datetime.now(timezone.utc)
        self.closed = False

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) - self.created_at > _TTL

    def notify(self, event_type: str, payload: dict) -> dict:
        """追加一条 notify 消息，返回该消息的完整格式。"""
        seq = self._next_seq
        self._next_seq += 1

        msg = {
            "type": "notify",
            "stream_id": self.stream_id,
            "sequence": seq,
            "event_type": event_type,
            "payload": payload,
        }

        self._messages[seq] = msg

        # ring buffer: 超过上限时淘汰最旧的
        while len(self._messages) > _MAX_BUFFER:
            self._messages.popitem(last=False)

        return msg

    def replay_from(self, from_sequence: int) -> list[dict] | dict:
        """从指定 sequence 开始回放。

        返回消息列表；若请求的 sequence 在 buffer 窗口外则返回 gap 信号。
        """
        if not self._messages:
            return {
                "type": "gap",
                "stream_id": self.stream_id,
                "from_sequence": from_sequence,
            }

        oldest_seq = next(iter(self._messages))
        newest_seq = next(iter(reversed(self._messages)))

        # 请求的 sequence 在 buffer 最新之后 → 没有可回放的消息
        if from_sequence > newest_seq:
            return {
                "type": "gap",
                "stream_id": self.stream_id,
                "from_sequence": from_sequence,
            }

        # from_sequence < oldest_seq：消息已被淘汰，从最早可用的开始回放
        effective_start = max(from_sequence, oldest_seq)
        return [msg for seq, msg in self._messages.items() if seq >= effective_start]

    def started_response(self) -> dict:
        return {
            "type": "stream_started",
            "stream_id": self.stream_id,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
        }


class StreamManager:
    """管理活跃的流式通知流。"""

    def __init__(self) -> None:
        self._streams: dict[str, StreamBuffer] = {}

    def create_stream(self, aggregate_type: str, aggregate_id: str) -> StreamBuffer:
        """创建新流并返回其 buffer。"""
        buf = StreamBuffer(aggregate_type, aggregate_id)
        self._streams[buf.stream_id] = buf
        return buf

    def get_stream(self, stream_id: str) -> Optional[StreamBuffer]:
        return self._streams.get(stream_id)

    def close_stream(self, stream_id: str) -> bool:
        """标记流为 closed，buffer 保留至 TTL 过期。"""
        buf = self._streams.get(stream_id)
        if buf is None:
            return False
        buf.closed = True
        return True

    def cleanup_expired(self) -> int:
        """移除已过期的流，返回移除数量。"""
        expired_ids = [
            sid for sid, buf in self._streams.items()
            if buf.is_expired
        ]
        for sid in expired_ids:
            del self._streams[sid]
        return len(expired_ids)

    def start_stream(self, aggregate_type: str, aggregate_id: str) -> dict:
        """创建流并返回 stream_started 响应。"""
        buf = self.create_stream(aggregate_type, aggregate_id)
        return buf.started_response()
