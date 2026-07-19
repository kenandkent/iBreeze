"""P7-T2：职员 ↔ 会话线程绑定与惰性创建 + 单 active turn CAS + 九维分片。"""

from __future__ import annotations

import pytest

from acos.rpc.errors import AcosError, RT_SESSION_BUSY, RT_SESSION_READONLY, RT_SESSION_STALE
from acos.rpc.methods_session import SessionMethods
from tests.runtime.conftest import seed_company_employee

pytestmark = pytest.mark.asyncio


async def _methods(migrated_db, **kw) -> SessionMethods:
    db_path, company_root = migrated_db
    return SessionMethods(db_path, company_root)


async def test_lazy_create_then_reuse(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path)
    p = {"company_id": "co1", "employee_id": "emp1", "message": "hi", "provider_id": "fake", "model_id": "m1"}
    r1 = await m._send_message(p)
    r2 = await m._send_message(p)
    assert r1["thread_id"] == r2["thread_id"]


async def test_cross_task_isolation(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path)
    base = {"company_id": "co1", "employee_id": "emp1", "provider_id": "fake", "model_id": "m1"}
    r_gen = await m._send_message({**base, "message": "通用", "task_id": None})
    r_t1 = await m._send_message({**base, "message": "任务1", "task_id": "task-A"})
    r_t2 = await m._send_message({**base, "message": "任务2", "task_id": "task-B"})
    assert len({r_gen["thread_id"], r_t1["thread_id"], r_t2["thread_id"]}) == 3
    # 各自 transcript 不串线
    g = await m._transcript_get({"thread_id": r_gen["thread_id"], "employee_id": "emp1"})
    assert any("通用" in l["content"] for l in g["transcript"])
    assert all("任务" not in l["content"] for l in g["transcript"])


async def test_concurrent_busy(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path)
    # 先创建真实线程
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "first",
        "provider_id": "fake", "model_id": "m1",
    })
    tid = r["thread_id"]
    # 手动占用 active turn（key 与 send_message 重算一致）
    await m._store.acquire_active_turn(
        tid, "turn-held", expected_version=int((await m._store.get_thread(tid))["version"])
    )
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "thread_id": tid, "message": "x",
            "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_BUSY


async def test_stale_on_context_change(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path)
    # 创建 model m1 的线程
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    # 现在用 model m2 发送，key 变化 → STALE
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "thread_id": r["thread_id"],
            "message": "y", "provider_id": "fake", "model_id": "m2",
        })
    assert exc.value.code == RT_SESSION_STALE


async def test_readonly_on_archived(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    await m._store.transition_status(r["thread_id"], "archived", expected_version=int(
        (await m._store.get_thread(r["thread_id"]))["version"]
    ))
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "thread_id": r["thread_id"],
            "message": "y", "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_READONLY
    # 但 transcript 仍可读
    g = await m._transcript_get({"thread_id": r["thread_id"], "employee_id": "emp1"})
    assert g["total"] >= 1


async def test_capability_upgrade_new_thread(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path, capability_snapshot='{"v":1}')
    r1 = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    # 升级 capability
    import aiosqlite
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute(
            "UPDATE employees SET capability_snapshot = ? WHERE employee_id = 'emp1'",
            ('{"v":2}',),
        )
        await db.commit()
    r2 = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "y",
        "provider_id": "fake", "model_id": "m1",
    })
    assert r1["thread_id"] != r2["thread_id"]


async def test_cross_employee_thread_rejected(migrated_db) -> None:
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path, employee_id="emp1")
    await seed_company_employee(m._db_path, employee_id="emp2", department_id="dep2")
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp2", "thread_id": r["thread_id"],
            "message": "y", "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == "ORG-PERM-DENIED"


async def test_effective_grants_isolation(migrated_db) -> None:
    """临时跨部门授权得到新线程；撤销后再次得到新线程（旧线程 transcript 不泄漏）。"""
    m = await _methods(migrated_db)
    await seed_company_employee(m._db_path)
    import aiosqlite
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    # 建一个 active grant
    grant_id = str(uuid.uuid4())
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute(
            """INSERT INTO access_grants (grant_id, company_id, employee_id, target_type,
               target_id, permission, status, expires_at, approved_by, version, created_at)
               VALUES (?, 'co1', 'emp1', 'department', 'depX', 'department_read', 'active',
                       '2099-01-01T00:00:00+00:00', 'system', 1, ?)""",
            (grant_id, now),
        )
        await db.commit()
    r_with = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "with-grant",
        "provider_id": "fake", "model_id": "m1",
    })
    # 撤销 grant
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute("UPDATE access_grants SET status='revoked' WHERE grant_id=?", (grant_id,))
        await db.commit()
    r_without = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "no-grant",
        "provider_id": "fake", "model_id": "m1",
    })
    assert r_with["thread_id"] != r_without["thread_id"]
    # 旧线程 transcript 里的哨兵不应出现在新线程发给 Provider 的上下文
    ctx = await m._call_provider(r_without["thread_id"], "probe", "co1", "fake", "m1")
    assert "with-grant" not in ctx["provider_context"]
