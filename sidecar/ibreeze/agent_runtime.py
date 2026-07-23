"""Agent Runtime Gateway 领域服务。

管理 Agent 生命周期、状态查询、运行列表和停止能力。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    AgentResponse,
    AgentRunRequest,
    AgentRunResponse,
)


# ── 内存存储 ──────────────────────────────────────────────────────────────

_agents: dict[str, dict[str, Any]] = {}
_agent_runs: dict[str, dict[str, Any]] = {}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── Agent CRUD ────────────────────────────────────────────────────────────

def register_agent(
    agent_id: str,
    name: str,
    model: str,
) -> AgentResponse:
    """注册 Agent（由系统调用）。"""
    now = _now_utc()

    record: dict[str, Any] = {
        "id": agent_id,
        "name": name,
        "status": "idle",
        "model": model,
        "created_at": now,
        "updated_at": now,
    }
    _agents[agent_id] = record
    return AgentResponse(**record)


def list_agents() -> list[AgentResponse]:
    """列出所有已注册的 Agent。"""
    return [AgentResponse(**a) for a in _agents.values()]


def get_agent_status(agent_id: str) -> AgentResponse:
    """查询 Agent 状态。"""
    record = _agents.get(agent_id)
    if record is None:
        raise KeyError(f"Agent 不存在: {agent_id}")
    return AgentResponse(**record)


# ── 运行管理 ──────────────────────────────────────────────────────────────

def run_agent(
    agent_id: str,
    user_id: str,
    message: str,
) -> AgentRunResponse:
    """启动 Agent 运行，返回运行 ID 和响应。

    实际 Agent 执行由 Runtime Gateway 的 adapter 调度，
    此处为简化的同步占位实现。
    """
    agent = _agents.get(agent_id)
    if agent is None:
        raise KeyError(f"Agent 不存在: {agent_id}")

    import uuid

    run_id = str(uuid.uuid4())
    now = _now_utc()

    # 更新 Agent 状态
    agent["status"] = "running"
    agent["updated_at"] = now

    run_record: dict[str, Any] = {
        "id": run_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "status": "completed",
        "response": f"[占位] Agent {agent['name']} 已收到消息: {message[:100]}",
        "started_at": now,
        "completed_at": now,
    }
    _agent_runs[run_id] = run_record

    # 恢复空闲
    agent["status"] = "idle"
    agent["updated_at"] = _now_utc()

    return AgentRunResponse(**run_record)


def stop_agent(agent_id: str) -> None:
    """停止正在运行的 Agent。"""
    agent = _agents.get(agent_id)
    if agent is None:
        raise KeyError(f"Agent 不存在: {agent_id}")

    if agent["status"] != "running":
        raise ValueError(f"Agent {agent_id} 当前未在运行 (状态: {agent['status']})")

    agent["status"] = "idle"
    agent["updated_at"] = _now_utc()

    # 取消所有未完成的运行
    for run in _agent_runs.values():
        if run["agent_id"] == agent_id and run["status"] == "running":
            run["status"] = "cancelled"
            run["completed_at"] = _now_utc()


def get_run_history(agent_id: str | None = None) -> list[AgentRunResponse]:
    """获取运行历史，可按 Agent 过滤。"""
    runs = sorted(
        [
            r
            for r in _agent_runs.values()
            if agent_id is None or r["agent_id"] == agent_id
        ],
        key=lambda r: r["started_at"],
        reverse=True,
    )
    return [AgentRunResponse(**r) for r in runs]
