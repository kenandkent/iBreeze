"""会话服务测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.rpc.errors import AcosError
from acos.sessions.service import SessionService
from acos.store.migrator import Migrator


@pytest.fixture
async def svc(tmp_path: Path) -> SessionService:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return SessionService(str(db_path))


async def test_create_thread(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert thread.thread_id
    assert thread.company_id == "co-1"
    assert thread.employee_id == "emp-1"
    assert thread.security_context_key == "key-a"
    assert thread.status == "active"
    assert thread.version == 1


async def test_get_existing_thread(svc: SessionService) -> None:
    t1 = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    t2 = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert t1.thread_id == t2.thread_id


async def test_different_key_creates_different_thread(svc: SessionService) -> None:
    t1 = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    t2 = await svc.get_or_create_thread("co-1", "emp-1", "key-b")
    assert t1.thread_id != t2.thread_id


async def test_send_message(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    turn = await svc.send_message(thread.thread_id, "你好")
    assert turn.turn_id
    assert turn.thread_id == thread.thread_id
    assert turn.content == "你好"
    assert turn.role == "user"
    assert turn.status == "pending"

    updated = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert updated.last_checkpoint_offset == 1


async def test_send_message_to_nonexistent_thread(svc: SessionService) -> None:
    with pytest.raises(AcosError) as exc_info:
        await svc.send_message("nonexistent", "你好")
    assert exc_info.value.code == "ORG-NOT-FOUND"


async def test_send_message_to_inactive_thread(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    await svc.archive_thread(thread.thread_id)
    with pytest.raises(AcosError) as exc_info:
        await svc.send_message(thread.thread_id, "不应成功")
    assert exc_info.value.code == "ORG-STATE-INVALID"


async def test_get_thread_history(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    await svc.send_message(thread.thread_id, "消息1")
    await svc.send_message(thread.thread_id, "消息2")
    await svc.send_message(thread.thread_id, "消息3", role="assistant")

    history = await svc.get_thread_history(thread.thread_id)
    assert len(history) == 3
    assert history[0].content == "消息1"
    assert history[1].content == "消息2"
    assert history[2].role == "assistant"


async def test_get_thread_history_limit(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    for i in range(5):
        await svc.send_message(thread.thread_id, f"消息{i}")

    history = await svc.get_thread_history(thread.thread_id, limit=2)
    assert len(history) == 2


async def test_archive_thread(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    await svc.archive_thread(thread.thread_id)
    latest = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert latest.thread_id != thread.thread_id


async def test_dormant_thread(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    await svc.dormant_thread(thread.thread_id)
    latest = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert latest.thread_id != thread.thread_id


async def test_archive_nonexistent_thread(svc: SessionService) -> None:
    with pytest.raises(AcosError) as exc_info:
        await svc.archive_thread("nonexistent")
    assert exc_info.value.code == "ORG-NOT-FOUND"


async def test_security_context_isolation(svc: SessionService) -> None:
    t_a = await svc.get_or_create_thread("co-1", "emp-1", "secret-a")
    t_b = await svc.get_or_create_thread("co-1", "emp-1", "secret-b")

    await svc.send_message(t_a.thread_id, "机密消息A")
    await svc.send_message(t_b.thread_id, "机密消息B")

    history_a = await svc.get_thread_history(t_a.thread_id)
    history_b = await svc.get_thread_history(t_b.thread_id)

    assert len(history_a) == 1
    assert history_a[0].content == "机密消息A"
    assert history_a[0].security_context_key == "secret-a"

    assert len(history_b) == 1
    assert history_b[0].content == "机密消息B"
    assert history_b[0].security_context_key == "secret-b"


async def test_thread_version_increments(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert thread.version == 1

    await svc.send_message(thread.thread_id, "msg1")
    updated = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    assert updated.version == 2


async def test_empty_history(svc: SessionService) -> None:
    thread = await svc.get_or_create_thread("co-1", "emp-1", "key-a")
    history = await svc.get_thread_history(thread.thread_id)
    assert history == []
