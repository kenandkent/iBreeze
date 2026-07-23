"""知识管理领域服务。

提供知识条目 CRUD（FAQ/DOC/URL）、内容 SHA-256 去重、标签管理、
版本控制、归档、全文搜索和统计能力。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    KnowledgeEntryCreate,
    KnowledgeEntryResponse,
    KnowledgeEntryUpdate,
    KnowledgeStatus,
    KnowledgeStatsResponse,
    KnowledgeType,
)


# ── 内存存储 ──────────────────────────────────────────────────────────────

_knowledge_entries: dict[str, dict[str, Any]] = {}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


def _compute_sha256(content: str) -> str:
    """计算内容的 SHA-256 哈希值"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── CRUD ──────────────────────────────────────────────────────────────────

def create_knowledge_entry(
    title: str,
    content: str,
    type: KnowledgeType,
    tags: list[str] | None = None,
) -> KnowledgeEntryResponse:
    """创建知识条目。

    自动计算内容 SHA-256 哈希，相同哈希的条目视为重复。
    """
    content_hash = _compute_sha256(content)

    # 内容去重检查
    for entry in _knowledge_entries.values():
        if (
            not entry["is_deleted"]
            and entry["content_sha256"] == content_hash
            and entry["type"] == type
        ):
            raise ValueError(f"内容重复: SHA-256={content_hash[:16]}... 已存在")

    import uuid

    entry_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": entry_id,
        "title": title,
        "content": content,
        "type": type,
        "status": KnowledgeStatus.ACTIVE,
        "content_sha256": content_hash,
        "tags": tags or [],
        "version": 1,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _knowledge_entries[entry_id] = record
    return KnowledgeEntryResponse(**record)


def list_knowledge_entries(
    type: KnowledgeType | None = None,
    status: KnowledgeStatus | None = None,
    tag: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[KnowledgeEntryResponse]:
    """分页列出知识条目，可按类型、状态、标签过滤。"""
    active = [
        e
        for e in _knowledge_entries.values()
        if not e["is_deleted"]
        and (type is None or e["type"] == type)
        and (status is None or e["status"] == status)
        and (tag is None or tag in e["tags"])
    ]
    return [KnowledgeEntryResponse(**e) for e in active[offset : offset + limit]]


def get_knowledge_entry(entry_id: str) -> KnowledgeEntryResponse:
    """获取单个知识条目详情。"""
    record = _knowledge_entries.get(entry_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"知识条目不存在: {entry_id}")
    return KnowledgeEntryResponse(**record)


def update_knowledge_entry(
    entry_id: str,
    data: KnowledgeEntryUpdate,
) -> KnowledgeEntryResponse:
    """更新知识条目。

    内容变更时重新计算 SHA-256 并进行去重检查，版本号自动递增。
    """
    record = _knowledge_entries.get(entry_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"知识条目不存在: {entry_id}")

    update_data = data.model_dump(exclude_unset=True)

    # 检查内容是否变更
    content_changed = "content" in update_data and update_data["content"] != record["content"]

    for key, value in update_data.items():
        record[key] = value

    # 内容变更：重新计算 SHA-256 并去重
    if content_changed:
        new_hash = _compute_sha256(record["content"])
        for other in _knowledge_entries.values():
            if (
                other["id"] != entry_id
                and not other["is_deleted"]
                and other["content_sha256"] == new_hash
                and other["type"] == record["type"]
            ):
                raise ValueError(f"内容重复: SHA-256={new_hash[:16]}... 已存在")
        record["content_sha256"] = new_hash
        record["version"] += 1

    record["updated_at"] = _now_utc()
    return KnowledgeEntryResponse(**record)


def archive_knowledge_entry(entry_id: str) -> KnowledgeEntryResponse:
    """归档知识条目。"""
    record = _knowledge_entries.get(entry_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"知识条目不存在: {entry_id}")

    record["status"] = KnowledgeStatus.ARCHIVED
    record["updated_at"] = _now_utc()
    return KnowledgeEntryResponse(**record)


# ── 搜索 ──────────────────────────────────────────────────────────────────

def search_knowledge_entries(
    query: str,
    type: KnowledgeType | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[KnowledgeEntryResponse]:
    """全文搜索知识条目（基于标题和内容的简单匹配）。"""
    query_lower = query.lower()
    results: list[dict[str, Any]] = []

    for entry in _knowledge_entries.values():
        if entry["is_deleted"] or entry["status"] != KnowledgeStatus.ACTIVE:
            continue
        if type is not None and entry["type"] != type:
            continue

        if query_lower in entry["title"].lower() or query_lower in entry["content"].lower():
            results.append(entry)

    return [KnowledgeEntryResponse(**e) for e in results[offset : offset + limit]]


# ── 统计 ──────────────────────────────────────────────────────────────────

def get_knowledge_stats() -> KnowledgeStatsResponse:
    """获取知识库统计信息。"""
    active_entries = [e for e in _knowledge_entries.values() if not e["is_deleted"]]

    total = len(active_entries)
    active_count = sum(1 for e in active_entries if e["status"] == KnowledgeStatus.ACTIVE)
    archived_count = sum(1 for e in active_entries if e["status"] == KnowledgeStatus.ARCHIVED)

    by_type: dict[str, int] = {}
    for e in active_entries:
        t = e["type"].value
        by_type[t] = by_type.get(t, 0) + 1

    by_tag: dict[str, int] = {}
    for e in active_entries:
        for tag in e["tags"]:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    return KnowledgeStatsResponse(
        total=total,
        active=active_count,
        archived=archived_count,
        by_type=by_type,
        by_tag=by_tag,
    )
