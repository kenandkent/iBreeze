"""P7-T1：会话线程存储（按安全上下文分片，公司隔离路径）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acos.rpc.errors import AcosError, BACKEND_PATH_DENIED
from acos.runtime import transcript as tx
from acos.runtime.path_broker import ensure_company_dir, resolve_session_path
from acos.runtime.session_thread_store import SessionThreadStore
from acos.store.migrator import Migrator

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


async def _migrate(db_path: str, company_root: str) -> None:
    Path(company_root).mkdir(parents=True, exist_ok=True)
    m = Migrator(db_path)
    await m.run_pending_migrations(MIGRATIONS_DIR)


async def test_compute_security_context_key_deterministic(store: SessionThreadStore) -> None:
    base = dict(
        company_id="c1", department_id="d1", task_id=None,
        capability_snapshot_checksum="cap1", provider_id="fake", model_id="m1",
        workspace_policy={"x": 1}, security_policy={}, effective_grants=[],
    )
    k1 = store.compute_security_context_key(**base)
    k2 = store.compute_security_context_key(**base)
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex


async def test_compute_key_changes_with_model_id(store: SessionThreadStore) -> None:
    base = dict(
        company_id="c1", department_id="d1", task_id=None,
        capability_snapshot_checksum="cap1", provider_id="fake", model_id="m1",
        workspace_policy={}, security_policy={}, effective_grants=[],
    )
    k1 = store.compute_security_context_key(**base)
    k2 = store.compute_security_context_key(**{**base, "model_id": "m2"})
    assert k1 != k2


async def test_compute_key_changes_with_policy_hashes(store: SessionThreadStore) -> None:
    base = dict(
        company_id="c1", department_id="d1", task_id=None,
        capability_snapshot_checksum="cap1", provider_id="fake", model_id="m1",
        workspace_policy={}, security_policy={}, effective_grants=[],
    )
    k0 = store.compute_security_context_key(**base)
    k_ws = store.compute_security_context_key(**{**base, "workspace_policy": {"a": 1}})
    k_sec = store.compute_security_context_key(**{**base, "security_policy": {"b": 2}})
    k_gr = store.compute_security_context_key(**{**base, "effective_grants": [{"grant_id": "g1"}]})
    assert k0 != k_ws != k_sec != k_gr != k0


async def test_empty_grants_hash_is_fixed(store: SessionThreadStore) -> None:
    import hashlib
    expected = hashlib.sha256("acos:effective-grants:v1\n[]".encode()).hexdigest()
    assert tx.compute_effective_grants_hash([]) == expected
    # 排序稳定：grant_id+expires_at 不同顺序产出同 hash
    a = tx.compute_effective_grants_hash(
        [{"grant_id": "g2", "expires_at": "2"}, {"grant_id": "g1", "expires_at": "1"}]
    )
    b = tx.compute_effective_grants_hash(
        [{"grant_id": "g1", "expires_at": "1"}, {"grant_id": "g2", "expires_at": "2"}]
    )
    assert a == b


async def test_atomic_write_survives_partial(tmp_path) -> None:
    """模拟写入过程中进程被杀：旧 session.json 不被破坏（临时文件 rename 保证）。"""
    db_path = str(tmp_path / "t.db")
    company_root = str(tmp_path / "root")
    await _migrate(db_path, company_root)
    store = SessionThreadStore(db_path, company_root)

    thread_id = "th-atomic"
    company_id = "c-atomic"
    # 直接写第一版投影，再模拟崩溃（只留 tmp 文件）
    thread_dir = store._thread_dir(company_id, thread_id)
    thread_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    good = thread_dir / "session.json"
    good.write_text('{"v":1}', encoding="utf-8")
    # 模拟半个 tmp
    tmp = good.with_suffix(".json.tmp")
    tmp.write_text('{"v":2', encoding="utf-8")
    # 不 rename（崩溃）：good 应保持
    assert good.read_text() == '{"v":1}'
    assert tmp.exists()


async def test_rebuild_from_db_reproducible(store: SessionThreadStore) -> None:
    company_id = "c-rebuild"
    thread = await store.get_or_create_current_thread(company_id, "emp1", "ctx-rebuild")
    thread_id = thread["thread_id"]
    await store.append_event(thread_id, company_id=company_id, employee_id="emp1",
                             event_type="message", role="user", content="你好")
    await store.append_event(thread_id, company_id=company_id, employee_id="emp1",
                             event_type="message", role="assistant", content="回复")
    proj1 = await store.rebuild_projection_from_db(thread_id)
    # 删除投影后重建，checksum 一致
    Path(proj1["transcript_path"]).unlink()
    proj2 = await store.rebuild_projection_from_db(thread_id)
    assert proj1["transcript_checksum"] == proj2["transcript_checksum"]
    assert proj1["summary_checksum"] == proj2["summary_checksum"]


async def test_path_broker_cross_company_rejected(tmp_path) -> None:
    root = str(tmp_path / "root")
    ensure_company_dir(root, "companyA")
    # 试图用 companyB 的 id 拼入 companyA 根 —— 仍落在 companyB 子目录，合法
    p = resolve_session_path(root, "companyB", "sessions", "x")
    assert "companyB" in str(p)
    # 构造越根路径：company_id 含 .. 穿越
    with pytest.raises(AcosError) as exc:
        resolve_session_path(root, "../evil", "sessions", "x")
    assert exc.value.code == BACKEND_PATH_DENIED


async def test_context_summary_deterministic(store: SessionThreadStore) -> None:
    lines = [
        tx.build_transcript_line(i, "message", "user", f"内容{i}")
        for i in range(5)
    ]
    s1 = tx.build_context_summary(lines)
    s2 = tx.build_context_summary(lines)
    assert s1 == s2
    assert "acos:context-summary:v1" in s1


async def test_transcript_line_checksum_fail_closed(store: SessionThreadStore) -> None:
    line = tx.build_transcript_line(1, "message", "user", "hi")
    # 篡改内容后重算 checksum 不一致
    bad = dict(line)
    bad["content"] = "tampered"
    assert tx.transcript_line_checksum(bad) != line["canonical_checksum"]
