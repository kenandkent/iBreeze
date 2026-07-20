"""session.* 覆盖率补充测试：list/get/cancel/transcript.get/resume、
安全上下文重算、SC-40-2 READONLY 分支、SC-40-3 服务端权威、内部端口参数校验。

仅测试，不改业务代码。SessionMethods 使用默认 require_backend=False。
"""

from __future__ import annotations

import aiosqlite
import pytest

from acos.rpc.errors import (
    AcosError,
    ORG_NOT_FOUND,
    ORG_PERM_DENIED,
    RT_SESSION_BUSY,
    RT_SESSION_NOT_FOUND,
    RT_SESSION_READONLY,
    RT_SESSION_STALE,
)
from acos.rpc.methods_session import (
    RT_DRAIN_TOKEN_INVALID,
    SessionMethods,
)
from tests.runtime.conftest import seed_company_employee

pytestmark = pytest.mark.asyncio


async def _m(migrated_db) -> SessionMethods:
    db_path, root = migrated_db
    m = SessionMethods(db_path, root)
    await seed_company_employee(db_path)
    return m


async def _seed_template(db_path: str, template_id: str, status: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO employee_templates
               (template_id, company_id, capability_id, capability_version,
                default_role, status, version, created_at, updated_at)
               VALUES (?, 'co1', 'cap', 1, '员工', ?, 1, datetime('now'), datetime('now'))""",
            (template_id, status),
        )
        await db.commit()


# ── register_to ─────────────────────────────────────────

async def test_register_to_registers_all_methods(migrated_db) -> None:
    m = await _m(migrated_db)
    registered: dict[str, object] = {}

    class _Server:
        def register_method(self, name, fn):
            registered[name] = fn

    m.register_to(_Server())
    for name in (
        "session.list", "session.get", "session.sendMessage", "session.cancel",
        "session.transcript.get", "session.resume", "session._suspend",
        "session._archive", "session._handoff", "session._reconcile",
    ):
        assert name in registered


# ── session.list ────────────────────────────────────────

async def test_list_requires_params(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._list({"company_id": "co1"})
    assert exc.value.code == "RT-VALIDATION"


async def test_list_returns_threads(migrated_db) -> None:
    m = await _m(migrated_db)
    await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    r = await m._list({"company_id": "co1", "employee_id": "emp1"})
    assert r["total"] == len(r["threads"]) >= 1


async def test_list_include_archived(migrated_db) -> None:
    m = await _m(migrated_db)
    await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    await m._archive({"employee_id": "emp1"})
    without = await m._list({"company_id": "co1", "employee_id": "emp1"})
    with_arch = await m._list({
        "company_id": "co1", "employee_id": "emp1", "include_archived": True,
    })
    assert with_arch["total"] >= without["total"]


# ── session.get ─────────────────────────────────────────

async def test_get_requires_thread_id(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._get({})
    assert exc.value.code == "RT-VALIDATION"


async def test_get_not_found(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._get({"thread_id": "nope"})
    assert exc.value.code == RT_SESSION_NOT_FOUND


async def test_get_returns_thread(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    got = await m._get({"thread_id": r["thread_id"], "employee_id": "emp1"})
    assert got["thread"]["thread_id"] == r["thread_id"]


async def test_get_cross_employee_denied(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    with pytest.raises(AcosError) as exc:
        await m._get({"thread_id": r["thread_id"], "employee_id": "other"})
    assert exc.value.code == ORG_PERM_DENIED


# ── session.cancel ──────────────────────────────────────

async def test_cancel_requires_thread_id(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._cancel({})
    assert exc.value.code == "RT-VALIDATION"


async def test_cancel_without_turn_force_release(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    res = await m._cancel({"thread_id": r["thread_id"]})
    assert res["thread_id"] == r["thread_id"]
    assert "cancelled" in res


async def test_cancel_with_active_turn(migrated_db) -> None:
    m = await _m(migrated_db)
    thread = await m._store.get_or_create_current_thread("co1", "emp1", "ctx-c")
    tid = thread["thread_id"]
    turn_id = "turn-a"
    await m._store.acquire_active_turn(tid, turn_id, expected_version=int(thread["version"]))
    got = await m._store.get_thread(tid)
    res = await m._cancel({"thread_id": tid, "turn_id": turn_id})
    assert res["cancelled"] is True
    assert got["active_turn_id"] == turn_id


async def test_cancel_wrong_turn_busy(migrated_db) -> None:
    m = await _m(migrated_db)
    thread = await m._store.get_or_create_current_thread("co1", "emp1", "ctx-c2")
    tid = thread["thread_id"]
    await m._store.acquire_active_turn(tid, "turn-real", expected_version=int(thread["version"]))
    with pytest.raises(AcosError) as exc:
        await m._cancel({"thread_id": tid, "turn_id": "turn-wrong"})
    assert exc.value.code == RT_SESSION_BUSY


# ── session.transcript.get ──────────────────────────────

async def test_transcript_requires_thread_id(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._transcript_get({})
    assert exc.value.code == "RT-VALIDATION"


async def test_transcript_returns_lines(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "hi",
        "provider_id": "fake", "model_id": "m1",
    })
    tr = await m._transcript_get({"thread_id": r["thread_id"], "employee_id": "emp1"})
    assert tr["thread_id"] == r["thread_id"]
    assert tr["total"] == len(tr["transcript"]) >= 1


async def test_transcript_cross_employee_denied(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "hi",
        "provider_id": "fake", "model_id": "m1",
    })
    with pytest.raises(AcosError) as exc:
        await m._transcript_get({"thread_id": r["thread_id"], "employee_id": "other"})
    assert exc.value.code == "ORG-PERM-DENIED"


# ── session.resume ──────────────────────────────────────

async def test_resume_requires_thread_id(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._resume({})
    assert exc.value.code == "RT-VALIDATION"


async def test_resume_returns_result(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "hi",
        "provider_id": "fake", "model_id": "fake-model-1",
    })
    out = await m._resume({"thread_id": r["thread_id"], "token_budget": 4000})
    assert isinstance(out, dict)


# ── SC-40-2 READONLY 分支（require_backend=False 也生效）───

async def test_sc_40_2_suspended_employee_readonly(migrated_db) -> None:
    m = await _m(migrated_db)
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute("UPDATE employees SET status='suspended' WHERE employee_id='emp1'")
        await db.commit()
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "message": "x",
            "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_READONLY


async def test_sc_40_2_archived_template_readonly(migrated_db) -> None:
    db_path, root = migrated_db
    m = SessionMethods(db_path, root)
    await seed_company_employee(db_path)
    await _seed_template(db_path, "tpl", "archived")
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "message": "x",
            "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_READONLY


async def test_send_readonly_when_thread_dormant(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    tid = r["thread_id"]
    got = await m._store.get_thread(tid)
    await m._store.transition_status(tid, "dormant", expected_version=int(got["version"]))
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "thread_id": tid,
            "message": "y", "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_READONLY


# ── SC-40-3：安全上下文服务端权威（伪造 key 被忽略）───────

async def test_forged_security_key_ignored(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
        "security_context_key": "forged-by-client",
    })
    thread = await m._store.get_thread(r["thread_id"])
    assert thread["security_context_key"] != "forged-by-client"


async def test_recompute_security_context(migrated_db) -> None:
    m = await _m(migrated_db)
    ctx_key, meta = await m._resolve_security_context(
        "co1", "emp1", None, "fake", "m1"
    )
    assert ctx_key
    assert "capability_snapshot_checksum" in meta
    assert "workspace_policy_hash" in meta
    assert "effective_grants_hash" in meta


async def test_recompute_security_context_employee_not_found(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._resolve_security_context("co1", "ghost", None, "fake", "m1")
    assert exc.value.code == ORG_NOT_FOUND


# ── 安全上下文变化 → STALE ────────────────────────────────

async def test_send_stale_when_context_key_changed(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    tid = r["thread_id"]
    async with aiosqlite.connect(m._db_path) as db:
        await db.execute(
            "UPDATE session_threads SET security_context_key='changed' WHERE thread_id=?",
            (tid,),
        )
        await db.commit()
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp1", "thread_id": tid,
            "message": "y", "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == RT_SESSION_STALE


async def test_send_thread_cross_employee_denied(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    await seed_company_employee(m._db_path, employee_id="emp2")
    with pytest.raises(AcosError) as exc:
        await m._send_message({
            "company_id": "co1", "employee_id": "emp2", "thread_id": r["thread_id"],
            "message": "y", "provider_id": "fake", "model_id": "m1",
        })
    assert exc.value.code == "ORG-PERM-DENIED"


# ── sendMessage 基础校验 ─────────────────────────────────

async def test_send_requires_company_and_employee(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._send_message({"message": "x"})
    assert exc.value.code == "RT-VALIDATION"


async def test_send_requires_message(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._send_message({"company_id": "co1", "employee_id": "emp1", "message": ""})
    assert exc.value.code == "RT-VALIDATION"


# ── 内部端口参数校验 ──────────────────────────────────────

async def test_suspend_missing_token_invalid(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._suspend({"employee_id": "emp1", "drain_id": "d1"})
    assert exc.value.code == RT_DRAIN_TOKEN_INVALID


async def test_archive_requires_employee(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._archive({})
    assert exc.value.code == "RT-VALIDATION"


async def test_handoff_requires_params(migrated_db) -> None:
    m = await _m(migrated_db)
    with pytest.raises(AcosError) as exc:
        await m._handoff_rpc({"employee_id": "emp1"})
    assert exc.value.code == "RT-VALIDATION"


async def test_reconcile_returns_results(migrated_db) -> None:
    m = await _m(migrated_db)
    r = await m._reconcile({})
    assert "results" in r


# ── lease 成功路径（seed 一个 healthy backend）────────────

async def _seed_backend(db_path: str, company_id: str = "co1") -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO backends
               (backend_id, company_id, name, backend_type, status, health_status,
                capabilities, concurrency_limit, version, created_at, updated_at)
               VALUES ('be1', ?, 'be', 'local_process', 'enabled', 'healthy',
                       '[]', 4, 1, datetime('now'), datetime('now'))""",
            (company_id,),
        )
        await db.commit()


async def test_send_message_with_backend_no_leftover_active_lease(migrated_db) -> None:
    # 即便公司存在 healthy backend，sendMessage 结束后也不应残留 active lease。
    # 注：当前 _try_acquire_lease 走降级路径（详见回报中的 BUG-1），故 lease 不会被 bind。
    m = await _m(migrated_db)
    await _seed_backend(m._db_path)
    r = await m._send_message({
        "company_id": "co1", "employee_id": "emp1", "message": "x",
        "provider_id": "fake", "model_id": "m1",
    })
    assert r["thread_id"]
    async with aiosqlite.connect(m._db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM backend_leases WHERE backend_id='be1' AND status='active'"
        )
        assert (await cur.fetchone())["c"] == 0
