"""P7-T3：原生恢复优先 + 规范化日志降级。"""

from __future__ import annotations

import pytest

from acos.providers.base import ProviderSession
from acos.providers.fake import FakeProviderAdapter
from acos.runtime.resume import resume_session
from acos.runtime.session_thread_store import SessionThreadStore
from tests.runtime.conftest import seed_company_employee

pytestmark = pytest.mark.asyncio


class NativeResumeFake(FakeProviderAdapter):
    """可控制原生 resume 成功/失败的测试 adapter。"""

    def __init__(self, support_native: bool = True) -> None:
        super().__init__()
        self.support_native = support_native
        self.resume_calls = 0
        self.create_calls = 0

    async def create_session(self, config):
        self.create_calls += 1
        return ProviderSession(
            native_session_id=f"native-{config.get('model','m')}",
            company_id=config.get("company_id", ""), provider_id="fake", model=config.get("model", "m"),
        )

    async def resume(self, checkpoint):
        if not self.support_native:
            raise RuntimeError("native resume unsupported")
        self.resume_calls += 1
        return ProviderSession(
            native_session_id="native-resumed", company_id="", provider_id="fake", model="m"
        )


async def _seed_thread(m: SessionThreadStore, db_path: str) -> str:
    await seed_company_employee(db_path)
    thread = await m.get_or_create_current_thread("co1", "emp1", "ctx-resume")
    tid = thread["thread_id"]
    await m.append_event(tid, company_id="co1", employee_id="emp1",
                         event_type="message", role="user", content="历史消息1")
    await m.append_event(tid, company_id="co1", employee_id="emp1",
                         event_type="message", role="assistant", content="回复1")
    return tid


async def test_native_resume_preferred(migrated_db) -> None:
    db_path, root = migrated_db
    m = SessionThreadStore(db_path, root)
    tid = await _seed_thread(m, db_path)
    adapter = NativeResumeFake(support_native=True)
    res = await resume_session(
        m, adapter, tid, company_id="co1", provider_id="fake", model="m1",
        token_budget=8000, checkpoint={"native_session_id": "abc"},
    )
    assert res["resume_mode"] == "native"
    assert res["used_fallback"] is False
    assert adapter.resume_calls == 1
    assert adapter.create_calls == 0


async def test_fallback_to_transcript(migrated_db) -> None:
    db_path, root = migrated_db
    m = SessionThreadStore(db_path, root)
    tid = await _seed_thread(m, db_path)
    adapter = NativeResumeFake(support_native=False)
    res = await resume_session(
        m, adapter, tid, company_id="co1", provider_id="fake", model="m1",
        token_budget=8000, checkpoint={"native_session_id": "abc"},
    )
    assert res["resume_mode"] == "transcript"
    assert res["used_fallback"] is True
    assert adapter.create_calls == 1
    # resume_mode 已写入 DB
    t = await m.get_thread(tid)
    assert t["resume_mode"] == "transcript"
    # 降级仍记录 RT-RESUME-FAILED 事件
    events = await m.get_events(tid)
    assert any(e["content"].startswith("RT-RESUME-FAILED") for e in events)


async def test_token_budget_truncates_tail(migrated_db) -> None:
    """超大单条消息：按 token 预算裁剪，不凑固定条数。"""
    db_path, root = migrated_db
    m = SessionThreadStore(db_path, root)
    tid = await _seed_thread(m, db_path)
    # 追加一条超大消息
    huge = "x" * 5000
    await m.append_event(tid, company_id="co1", employee_id="emp1",
                         event_type="message", role="user", content=huge)
    lines, _mode = await m.build_resume_context(tid, token_budget=50)
    # 预算极小，应只取到检查点后的少量内容（不把 5000 字全带上）
    total_tokens = sum(int(l["token_estimate"]) for l in lines)
    assert total_tokens <= 50 + max(int(l["token_estimate"]) for l in lines)
