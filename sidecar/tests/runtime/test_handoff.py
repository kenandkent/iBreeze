"""P7-T4：调岗 Handoff（安全关键：旧部门私有信息不泄漏到新线程）。"""

from __future__ import annotations

import json
import pytest

from acos.rpc.errors import AcosError
from acos.rpc.methods_session import SessionMethods
from acos.runtime.handoff import HandoffService
from acos.runtime.session_thread_store import SessionThreadStore
from tests.runtime.conftest import seed_company_employee

pytestmark = pytest.mark.asyncio

SECRET = "【旧部门私有机密-ZZZ】"


async def _setup(migrated_db, **kw) -> SessionMethods:
    db_path, root = migrated_db
    m = SessionMethods(db_path, root)
    await seed_company_employee(db_path, **kw)
    return m


async def test_no_cross_context_leak_on_transfer(migrated_db) -> None:
    """核心：旧通用线程 transcript 中的私有信息，不应出现在调岗后新线程发给 Provider 的上下文。"""
    m = await _setup(migrated_db)
    # 调岗前，在通用线程写入私有信息
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": f"请参考 {SECRET}",
        "provider_id": "fake", "model_id": "m1",
    })
    old_tid = r["thread_id"]

    # 执行调岗 Handoff
    out = await m._handoff_rpc({
        "employee_id": "emp1", "new_department_id": "dep2", "drain_id": "d1",
    })
    new_tid = out["new_thread_id"]
    assert new_tid != old_tid

    # 旧线程已 archived，新线程 active
    old_thread = await m._store.get_thread(old_tid)
    new_thread = await m._store.get_thread(new_tid)
    assert old_thread["status"] == "archived"
    assert new_thread["status"] == "active"

    # 新线程首次 sendMessage，检查发给 Provider 的上下文不含旧机密
    r2 = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "调岗后新问题",
        "provider_id": "fake", "model_id": "m1",
    })
    assert r2["thread_id"] == new_tid
    ctx = await m._call_provider(new_tid, "probe", "co1", "fake", "m1")
    assert SECRET not in ctx["provider_context"]
    # 旧线程 transcript 仍保留机密（证明归档而非删除）
    old_tr = await m._transcript_get({"thread_id": old_tid, "employee_id": "emp1"})
    assert any(SECRET in l["content"] for l in old_tr["transcript"])


async def test_old_thread_rejects_send_after_transfer(migrated_db) -> None:
    m = await _setup(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    old_tid = r["thread_id"]
    await m._handoff_rpc({"employee_id": "emp1", "new_department_id": "dep2", "drain_id": "d1"})
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "thread_id": old_tid,
            "message": "y", "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == "RT-SESSION-READONLY"


async def test_task_thread_untouched_by_handoff(migrated_db) -> None:
    """任务绑定的会话线程在调岗前后内容不变。"""
    m = await _setup(migrated_db)
    r_task = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "任务内容",
        "task_id": "task-1", "provider_id": "fake", "model_id": "m1",
    })
    task_tid = r_task["thread_id"]
    await m._handoff_rpc({"employee_id": "emp1", "new_department_id": "dep2", "drain_id": "d1"})
    # 任务线程仍 active 且内容不变
    t = await m._store.get_thread(task_tid)
    assert t["status"] == "active"
    tr = await m._transcript_get({"thread_id": task_tid, "employee_id": "emp1"})
    assert any("任务内容" in l["content"] for l in tr["transcript"])


async def test_exactly_once_employee_transferred(migrated_db) -> None:
    """崩溃在'写完新线程但未提交 DB'时，对账器补完恰好一次 EmployeeTransferred。"""
    m = await _setup(migrated_db)
    await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    old_tid = (await m._store.get_thread(
        (await m._store.list_threads("co1", "emp1"))[0]["thread_id"]
    ))["thread_id"]
    # 模拟崩溃：手动写完整 staging + 置 transferring（不提交 handle_transfer 的 DB 事务）
    import aiosqlite
    from pathlib import Path
    _, root = migrated_db
    new_tid = "th-crash-new"
    staging = Path(root) / "co1" / "sessions" / "_staging" / "emp1"
    staging.mkdir(parents=True, exist_ok=True)
    sess = {
        "schema_version": "acos:session:v1", "thread_id": new_tid,
        "company_id": "co1", "employee_id": "emp1",
        "security_context_key": "ctx", "status": "active", "task_id": None,
    }
    (staging / "session.json").write_text(json.dumps(sess), encoding="utf-8")
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute(
            "UPDATE session_threads SET status='archived', archived_at='now' WHERE thread_id=?",
            (old_tid,),
        )
        await db.execute(
            "UPDATE employees SET session_transfer_state='transferring' WHERE employee_id='emp1'"
        )
        await db.commit()

    # 对账器第一次：补完
    r1 = await m._reconcile({})
    assert r1["results"][0]["outcome"] == "completed"
    # 对账器重跑：已 transferred → 无 transferring 职员，不重复
    r2 = await m._reconcile({})
    assert r2["results"] == []

    async with aiosqlite.connect(m._db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM session_transfer_journal WHERE employee_id='emp1' AND event_type='EmployeeTransferred'"
        )
        count = (await cur.fetchone())["c"]
    assert count == 1


async def test_reconcile_needs_repair_on_incomplete_staging(migrated_db) -> None:
    """模拟新线程 staging 写入中途崩溃、staging 不完整 → 对账器判 needs_repair。"""
    m = await _setup(migrated_db)
    await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    # 手动把 employee 置 transferring，并写入不完整的 staging
    import aiosqlite
    from pathlib import Path
    _, root = migrated_db
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute(
            "UPDATE employees SET session_transfer_state='transferring' WHERE employee_id='emp1'"
        )
        await db.commit()
    staging = Path(root) / "co1" / "sessions" / "_staging" / "emp1"
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "session.json").write_text('{broken', encoding="utf-8")

    results = await m._reconcile({})
    assert results["results"][0]["outcome"] == "needs_repair"

    async with aiosqlite.connect(m._db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT 1 FROM session_transfer_journal WHERE employee_id='emp1' AND event_type='EmployeeTransferNeedsRepair'"
        )
        assert await cur.fetchone() is not None
        cur = await db.execute(
            "SELECT session_transfer_state FROM employees WHERE employee_id='emp1'"
        )
        assert (await cur.fetchone())["session_transfer_state"] == "needs_repair"


async def test_handoff_updates_primary_thread_binding(migrated_db) -> None:
    m = await _setup(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    out = await m._handoff_rpc({"employee_id": "emp1", "new_department_id": "dep2", "drain_id": "d1"})
    import aiosqlite
    async with aiosqlite.connect(m._db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT primary_session_thread_id, session_transfer_state FROM employees WHERE employee_id='emp1'"
        )
        row = await cur.fetchone()
    assert row["primary_session_thread_id"] == out["new_thread_id"]
    assert row["session_transfer_state"] == "none"
