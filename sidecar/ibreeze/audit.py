"""本地审计领域服务。

提供 append-only 审计事件记录、按条件查询和时间段导出能力。
审计日志一旦写入不可修改、不可删除。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    AuditEventCreate,
    AuditEventResponse,
    AuditOutcome,
)


# ── 内存存储（append-only）──────────────────────────────────────────────

_audit_events: list[dict[str, Any]] = []
_sequence_counter: int = 0


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


def _next_sequence() -> int:
    """生成下一个序列号"""
    global _sequence_counter
    _sequence_counter += 1
    return _sequence_counter


# ── 公开接口 ──────────────────────────────────────────────────────────────

def log_event(
    event_type: str,
    actor_type: str,
    resource_type: str,
    outcome: AuditOutcome,
    actor_id: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
    company_id: str | None = None,
    timestamp: datetime | None = None,
) -> AuditEventResponse:
    """记录审计事件。

    append-only 模式：事件一旦写入不可修改、不可删除。
    detail 中的敏感信息（密码、Token、API Key、完整文件内容）
    应在调用前清理，仅保留哈希和相对路径。
    """
    import uuid

    event_id = str(uuid.uuid4())
    now = timestamp or _now_utc()
    seq = _next_sequence()

    # 审计 detail 写入前清理敏感字段
    sanitized_detail = _sanitize_detail(detail or {})

    record: dict[str, Any] = {
        "id": event_id,
        "row_sequence": seq,
        "company_id": company_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "outcome": outcome,
        "detail": sanitized_detail,
        "created_at": now,
    }
    _audit_events.append(record)
    return AuditEventResponse(**record)


def query_events(
    actor_id: str | None = None,
    resource_type: str | None = None,
    company_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[AuditEventResponse]:
    """按条件查询审计事件。

    支持按操作者 ID、资源类型、企业和时间范围过滤。
    """
    results = _audit_events

    if actor_id is not None:
        results = [e for e in results if e["actor_id"] == actor_id]
    if resource_type is not None:
        results = [e for e in results if e["resource_type"] == resource_type]
    if company_id is not None:
        results = [e for e in results if e["company_id"] == company_id]
    if start_time is not None:
        results = [e for e in results if e["created_at"] >= start_time]
    if end_time is not None:
        results = [e for e in results if e["created_at"] <= end_time]

    return [AuditEventResponse(**e) for e in results[offset : offset + limit]]


def export_events(
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    """导出指定时间段的审计事件为 JSON 数组。

    返回字典列表，每个字典包含完整的审计事件字段，
    适用于序列化为 JSON 文件。
    """
    results = [
        e for e in _audit_events if e["created_at"] >= start_time and e["created_at"] <= end_time
    ]

    # 转换为可序列化的字典
    exported: list[dict[str, Any]] = []
    for event in results:
        exported.append({
            "id": event["id"],
            "row_sequence": event["row_sequence"],
            "company_id": event["company_id"],
            "actor_type": event["actor_type"],
            "actor_id": event["actor_id"],
            "action": event["action"],
            "resource_type": event["resource_type"],
            "resource_id": event["resource_id"],
            "outcome": event["outcome"].value
            if isinstance(event["outcome"], AuditOutcome)
            else event["outcome"],
            "detail": event["detail"],
            "created_at": event["created_at"].isoformat(),
        })

    return exported


# ── 内部工具 ──────────────────────────────────────────────────────────────

_SENSITIVE_KEYS = frozenset({
    "password",
    "token",
    "api_key",
    "secret",
    "authorization",
    "content",
    "file_content",
})


def _sanitize_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """清理审计 detail 中的敏感字段。

    密码、Token、API Key 和完整文件正文被替换为哈希或占位符。
    """
    sanitized: dict[str, Any] = {}
    for key, value in detail.items():
        if key.lower() in _SENSITIVE_KEYS:
            if isinstance(value, str) and len(value) > 0:
                import hashlib
                sanitized[key] = f"[hash:{hashlib.sha256(value.encode()).hexdigest()[:16]}]"
            else:
                sanitized[key] = "[redacted]"
        else:
            sanitized[key] = value
    return sanitized
