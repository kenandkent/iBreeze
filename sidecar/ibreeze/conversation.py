"""对话管理领域服务。

提供对话 CRUD、消息添加（角色枚举 user/assistant/system/tool）、引用管理、
软删除、归档（archived 状态不可写）和全文搜索能力。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationStatus,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
    MessageRole,
)


# ── 内存存储 ──────────────────────────────────────────────────────────────

_conversations: dict[str, dict[str, Any]] = {}
_messages: dict[str, dict[str, Any]] = {}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── 对话 CRUD ─────────────────────────────────────────────────────────────

def create_conversation(
    company_id: str,
    title: str | None = None,
) -> ConversationResponse:
    """创建空对话。"""
    import uuid

    conv_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": conv_id,
        "company_id": company_id,
        "title": title,
        "status": ConversationStatus.ACTIVE,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _conversations[conv_id] = record
    return ConversationResponse(**record)


def list_conversations(
    company_id: str,
    status: ConversationStatus | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[ConversationResponse]:
    """分页列出对话，可按状态过滤。"""
    active = [
        c
        for c in _conversations.values()
        if not c["is_deleted"]
        and c["company_id"] == company_id
        and (status is None or c["status"] == status)
    ]
    return [ConversationResponse(**c) for c in active[offset : offset + limit]]


def get_conversation(conv_id: str) -> ConversationResponse:
    """获取单个对话详情。"""
    record = _conversations.get(conv_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"对话不存在: {conv_id}")
    return ConversationResponse(**record)


def update_conversation(
    conv_id: str,
    data: ConversationUpdate,
) -> ConversationResponse:
    """更新对话标题或状态。

    archived 状态的对话不允许修改。
    """
    record = _conversations.get(conv_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"对话不存在: {conv_id}")

    if record["status"] == ConversationStatus.ARCHIVED:
        raise ValueError("已归档的对话不可修改")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        record[key] = value
    record["updated_at"] = _now_utc()

    return ConversationResponse(**record)


def delete_conversation(conv_id: str) -> None:
    """软删除对话。"""
    record = _conversations.get(conv_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"对话不存在: {conv_id}")
    record["is_deleted"] = True
    record["updated_at"] = _now_utc()


def archive_conversation(conv_id: str) -> ConversationResponse:
    """归档对话。归档后不可写入新消息。"""
    record = _conversations.get(conv_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"对话不存在: {conv_id}")

    record["status"] = ConversationStatus.ARCHIVED
    record["updated_at"] = _now_utc()
    return ConversationResponse(**record)


# ── 消息管理 ──────────────────────────────────────────────────────────────

def add_message(
    conv_id: str,
    role: MessageRole,
    content: str,
    references: list[dict[str, Any]] | None = None,
) -> MessageResponse:
    """向对话添加消息。

    archived 状态的对话不允许添加消息。
    """
    conv = _conversations.get(conv_id)
    if conv is None or conv["is_deleted"]:
        raise KeyError(f"对话不存在: {conv_id}")

    if conv["status"] == ConversationStatus.ARCHIVED:
        raise ValueError("已归档的对话不可添加消息")

    import uuid

    msg_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": msg_id,
        "conversation_id": conv_id,
        "role": role,
        "content": content,
        "references": references or [],
        "is_deleted": False,
        "created_at": now,
    }
    _messages[msg_id] = record
    conv["updated_at"] = now
    return MessageResponse(**record)


def list_messages(
    conv_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[MessageResponse]:
    """列出对话消息（按时间正序）。"""
    if conv_id not in _conversations:
        raise KeyError(f"对话不存在: {conv_id}")

    msgs = sorted(
        [
            m
            for m in _messages.values()
            if m["conversation_id"] == conv_id and not m["is_deleted"]
        ],
        key=lambda m: m["created_at"],
    )
    return [MessageResponse(**m) for m in msgs[offset : offset + limit]]


def delete_message(msg_id: str) -> None:
    """软删除消息。"""
    record = _messages.get(msg_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"消息不存在: {msg_id}")
    record["is_deleted"] = True


# ── 搜索 ──────────────────────────────────────────────────────────────────

def search_conversations(
    company_id: str,
    query: str,
    offset: int = 0,
    limit: int = 20,
) -> list[ConversationResponse]:
    """全文搜索对话（基于标题和消息内容的简单匹配）。"""
    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    for conv in _conversations.values():
        if conv["is_deleted"] or conv["company_id"] != company_id:
            continue

        # 匹配标题
        if conv.get("title") and query_lower in conv["title"].lower():
            results.append(conv)
            continue

        # 匹配消息内容
        for msg in _messages.values():
            if (
                msg["conversation_id"] == conv["id"]
                and not msg["is_deleted"]
                and query_lower in msg["content"].lower()
            ):
                results.append(conv)
                break

    return [ConversationResponse(**c) for c in results[offset : offset + limit]]
