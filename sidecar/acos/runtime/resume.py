"""会话恢复策略（Phase 7-T3）。

恢复目标不是"最近 N 条"，而是"最近检查点 + 有界 tail"：
1. 优先调 ProviderAdapter.resume(checkpoint) 用原生 session id。
2. 失败或不支持原生会话时，加载最近检查点 + 之后有界 tail（按 token 预算裁剪），
   走 create_session 并把重建上下文作为初始输入，resume_mode 更新为 transcript。
3. 失败降级记录 RT-RESUME-FAILED，但不让整个请求失败——降级成功正常返回。

对应设计方案 §19 第 13 条。
"""

from __future__ import annotations

import uuid
from typing import Any

from acos.providers.base import ProviderAdapter
from acos.rpc.errors import AcosError, RT_RESUME_FAILED
from acos.runtime.session_thread_store import SessionThreadStore


async def resume_session(
    store: SessionThreadStore,
    adapter: ProviderAdapter,
    thread_id: str,
    *,
    company_id: str,
    provider_id: str,
    model: str,
    token_budget: int,
    checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """执行恢复：原生优先，降级到 transcript 重建。返回 {session_id, native, resume_mode}。"""
    thread = await store.get_thread(thread_id)
    native_session_id = thread.get("session_json_path")  # 占位：真实原生 id 由 runtime_sessions 提供

    # 1) 原生 resume 优先
    if checkpoint:
        try:
            provider_session = await adapter.resume(checkpoint)
            if provider_session is not None:
                # 原生恢复成功，直接返回（不做状态转换）
                return {
                    "thread_id": thread_id,
                    "native_session_id": provider_session.native_session_id,
                    "resume_mode": "native",
                    "used_fallback": False,
                }
        except Exception as exc:  # noqa: BLE001 — 降级路径必须吞异常
            # 记录 RT-RESUME-FAILED，但继续降级
            await _record_resume_failed(store, thread_id, cause=str(exc))

    # 2) 降级：检查点 + 有界 tail 重建
    lines, _mode = await store.build_resume_context(thread_id, token_budget=token_budget)
    initial_input = "\n".join(
        f"{ln['role'] or ln['event_type']}: {ln['content']}" for ln in lines
    )
    provider_session = await adapter.create_session({
        "company_id": company_id,
        "provider_id": provider_id,
        "model": model,
        "resume_mode": "transcript",
        "initial_input": initial_input,
    })
    # 更新 resume_mode 为 transcript
    import aiosqlite
    async with aiosqlite.connect(store._db_path) as db:
        await db.execute(
            "UPDATE session_threads SET resume_mode = 'transcript', version = version + 1 WHERE thread_id = ?",
            (thread_id,),
        )
        await db.commit()

    return {
        "thread_id": thread_id,
        "native_session_id": provider_session.native_session_id,
        "resume_mode": "transcript",
        "used_fallback": True,
        "initial_input": initial_input,
    }


async def _record_resume_failed(
    store: SessionThreadStore, thread_id: str, *, cause: str
) -> None:
    """记录 RT-RESUME-FAILED 事件（不抛异常）。"""
    import aiosqlite
    async with aiosqlite.connect(store._db_path) as db:
        await db.execute(
            """INSERT INTO conversation_events
               (event_id, thread_id, company_id, employee_id, sequence,
                schema_version, event_type, role, content, token_estimate,
                canonical_checksum, created_at)
               SELECT ?, thread_id, company_id, employee_id,
                      COALESCE(MAX(sequence),0)+1, 'acos:conversation-event:v1',
                      'system', 'system', ?, 0, '', ?
               FROM conversation_events WHERE thread_id = ?
               ON CONFLICT DO NOTHING""",
            (str(uuid.uuid4()), f"RT-RESUME-FAILED: {cause}", _now(), thread_id),
        )
        await db.commit()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
