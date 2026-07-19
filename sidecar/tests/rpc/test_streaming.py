"""流式通知协议测试。"""

from __future__ import annotations

from acos.rpc.streaming import StreamBuffer, StreamManager


# ── StreamBuffer ──────────────────────────────────────────────────────────


def test_stream_buffer_basic_notify() -> None:
    buf = StreamBuffer("task", "t-1")
    msg = buf.notify("task.started", {"task_id": "t-1"})
    assert msg["type"] == "notify"
    assert msg["stream_id"] == buf.stream_id
    assert msg["sequence"] == 1
    assert msg["event_type"] == "task.started"
    assert msg["payload"] == {"task_id": "t-1"}


def test_stream_buffer_monotonic_sequence() -> None:
    buf = StreamBuffer("task", "t-1")
    m1 = buf.notify("e1", {})
    m2 = buf.notify("e2", {})
    m3 = buf.notify("e3", {})
    assert m1["sequence"] == 1
    assert m2["sequence"] == 2
    assert m3["sequence"] == 3


def test_stream_buffer_replay_from_start() -> None:
    buf = StreamBuffer("task", "t-1")
    buf.notify("e1", {"a": 1})
    buf.notify("e2", {"a": 2})
    msgs = buf.replay_from(1)
    assert isinstance(msgs, list)
    assert len(msgs) == 2
    assert msgs[0]["sequence"] == 1
    assert msgs[1]["sequence"] == 2


def test_stream_buffer_replay_from_middle() -> None:
    buf = StreamBuffer("task", "t-1")
    buf.notify("e1", {})
    buf.notify("e2", {})
    buf.notify("e3", {})
    msgs = buf.replay_from(2)
    assert isinstance(msgs, list)
    assert len(msgs) == 2
    assert msgs[0]["sequence"] == 2
    assert msgs[1]["sequence"] == 3


def test_stream_buffer_gap_detection() -> None:
    buf = StreamBuffer("task", "t-1")
    buf.notify("e1", {})
    # 请求 sequence 5，但 buffer 最大只有 1 → gap
    result = buf.replay_from(5)
    assert isinstance(result, dict)
    assert result["type"] == "gap"
    assert result["stream_id"] == buf.stream_id
    assert result["from_sequence"] == 5


def test_stream_buffer_gap_on_empty_buffer() -> None:
    buf = StreamBuffer("task", "t-1")
    result = buf.replay_from(1)
    assert isinstance(result, dict)
    assert result["type"] == "gap"
    assert result["from_sequence"] == 1


def test_stream_buffer_replay_empty_from_start() -> None:
    buf = StreamBuffer("task", "t-1")
    result = buf.replay_from(1)
    assert isinstance(result, dict)
    assert result["type"] == "gap"


def test_stream_buffer_ring_eviction() -> None:
    buf = StreamBuffer("task", "t-1")
    # 写入 1005 条，应淘汰前 5 条
    for i in range(1005):
        buf.notify(f"e{i}", {"i": i})
    msgs = buf.replay_from(1)
    assert isinstance(msgs, list)
    assert len(msgs) == 1000
    # 最旧的 sequence 应该是 6（1-5 已被淘汰）
    assert msgs[0]["sequence"] == 6


def test_stream_buffer_started_response() -> None:
    buf = StreamBuffer("task", "t-1")
    resp = buf.started_response()
    assert resp["type"] == "stream_started"
    assert resp["stream_id"] == buf.stream_id
    assert resp["aggregate_type"] == "task"
    assert resp["aggregate_id"] == "t-1"


def test_stream_buffer_not_expired_initially() -> None:
    buf = StreamBuffer("task", "t-1")
    assert buf.is_expired is False


def test_stream_buffer_not_closed_initially() -> None:
    buf = StreamBuffer("task", "t-1")
    assert buf.closed is False


# ── StreamManager ─────────────────────────────────────────────────────────


def test_manager_create_stream() -> None:
    mgr = StreamManager()
    buf = mgr.create_stream("task", "t-1")
    assert buf.stream_id
    assert buf.aggregate_type == "task"
    assert buf.aggregate_id == "t-1"
    assert mgr.get_stream(buf.stream_id) is buf


def test_manager_get_stream_not_found() -> None:
    mgr = StreamManager()
    assert mgr.get_stream("nonexistent") is None


def test_manager_close_stream() -> None:
    mgr = StreamManager()
    buf = mgr.create_stream("task", "t-1")
    assert mgr.close_stream(buf.stream_id) is True
    assert buf.closed is True
    # 流仍在 dict 中（保留至 TTL）
    assert mgr.get_stream(buf.stream_id) is buf


def test_manager_close_nonexistent_stream() -> None:
    mgr = StreamManager()
    assert mgr.close_stream("nonexistent") is False


def test_manager_start_stream_response() -> None:
    mgr = StreamManager()
    resp = mgr.start_stream("task", "t-1")
    assert resp["type"] == "stream_started"
    assert isinstance(resp["stream_id"], str)
    assert resp["aggregate_type"] == "task"
    assert resp["aggregate_id"] == "t-1"


def test_manager_cleanup_expired() -> None:
    import time
    from datetime import timedelta

    mgr = StreamManager()
    buf = mgr.create_stream("task", "t-1")
    # 手动设置 created_at 为 6 分钟前使其过期
    buf.created_at = buf.created_at - timedelta(minutes=6)
    assert buf.is_expired is True

    # 创建一个未过期的
    mgr.create_stream("task", "t-2")

    removed = mgr.cleanup_expired()
    assert removed == 1
    # 只剩 t-2
    streams = list(mgr._streams.values())
    assert len(streams) == 1
    assert streams[0].aggregate_id == "t-2"


def test_manager_multiple_streams_independent() -> None:
    mgr = StreamManager()
    b1 = mgr.create_stream("task", "t-1")
    b2 = mgr.create_stream("task", "t-2")
    b1.notify("e1", {})
    b2.notify("e2", {})

    msgs1 = b1.replay_from(1)
    msgs2 = b2.replay_from(1)
    assert len(msgs1) == 1
    assert len(msgs2) == 1
    assert msgs1[0]["stream_id"] == b1.stream_id
    assert msgs2[0]["stream_id"] == b2.stream_id


def test_manager_replay_via_stream_id() -> None:
    mgr = StreamManager()
    buf = mgr.create_stream("task", "t-1")
    buf.notify("e1", {})
    buf.notify("e2", {})

    retrieved = mgr.get_stream(buf.stream_id)
    msgs = retrieved.replay_from(1)
    assert isinstance(msgs, list)
    assert len(msgs) == 2
