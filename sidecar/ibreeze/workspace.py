"""工作区管理领域服务。

提供工作区 CRUD、成员管理、配置管理和软删除能力。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    WorkspaceConfigResponse,
    WorkspaceConfigUpdate,
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberResponse,
    WorkspaceMemberRole,
    WorkspaceMemberRemove,
    WorkspaceResponse,
    WorkspaceUpdate,
)


# ── 内存存储 ──────────────────────────────────────────────────────────────

_workspaces: dict[str, dict[str, Any]] = {}
_workspace_members: dict[str, dict[str, Any]] = {}
_workspace_configs: dict[str, dict[str, dict[str, Any]]] = {}  # ws_id -> {key -> config}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── 工作区 CRUD ───────────────────────────────────────────────────────────

def create_workspace(
    company_id: str,
    name: str,
    description: str | None = None,
) -> WorkspaceResponse:
    """创建工作区。"""
    import uuid

    ws_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": ws_id,
        "company_id": company_id,
        "name": name,
        "description": description,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _workspaces[ws_id] = record
    _workspace_configs[ws_id] = {}
    return WorkspaceResponse(**record)


def list_workspaces(
    company_id: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[WorkspaceResponse]:
    """分页列出工作区，可按企业 ID 过滤。"""
    active = [
        w
        for w in _workspaces.values()
        if not w["is_deleted"] and (company_id is None or w["company_id"] == company_id)
    ]
    return [WorkspaceResponse(**w) for w in active[offset : offset + limit]]


def get_workspace(ws_id: str) -> WorkspaceResponse:
    """获取单个工作区详情。"""
    record = _workspaces.get(ws_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"工作区不存在: {ws_id}")
    return WorkspaceResponse(**record)


def update_workspace(ws_id: str, data: WorkspaceUpdate) -> WorkspaceResponse:
    """更新工作区信息。"""
    record = _workspaces.get(ws_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"工作区不存在: {ws_id}")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        record[key] = value
    record["updated_at"] = _now_utc()

    return WorkspaceResponse(**record)


def delete_workspace(ws_id: str) -> None:
    """软删除工作区。"""
    record = _workspaces.get(ws_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"工作区不存在: {ws_id}")
    record["is_deleted"] = True
    record["updated_at"] = _now_utc()


# ── 成员管理 ──────────────────────────────────────────────────────────────

def add_member(ws_id: str, data: WorkspaceMemberAdd) -> WorkspaceMemberResponse:
    """添加工作区成员。"""
    ws = _workspaces.get(ws_id)
    if ws is None or ws["is_deleted"]:
        raise KeyError(f"工作区不存在: {ws_id}")

    # 检查是否已存在
    for m in _workspace_members.values():
        if m["workspace_id"] == ws_id and m["user_id"] == data.user_id:
            raise ValueError(f"用户 {data.user_id} 已是工作区成员")

    import uuid

    member_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": member_id,
        "workspace_id": ws_id,
        "user_id": data.user_id,
        "role": data.role,
        "created_at": now,
    }
    _workspace_members[member_id] = record
    return WorkspaceMemberResponse(**record)


def remove_member(ws_id: str, user_id: str) -> None:
    """移除工作区成员。"""
    to_remove = None
    for m in _workspace_members.values():
        if m["workspace_id"] == ws_id and m["user_id"] == user_id:
            to_remove = m["id"]
            break

    if to_remove is None:
        raise KeyError(f"成员不存在: ws={ws_id}, user={user_id}")

    del _workspace_members[to_remove]


def list_members(ws_id: str) -> list[WorkspaceMemberResponse]:
    """列出工作区所有成员。"""
    members = [
        m for m in _workspace_members.values() if m["workspace_id"] == ws_id
    ]
    return [WorkspaceMemberResponse(**m) for m in members]


def update_member_role(
    ws_id: str, user_id: str, role: WorkspaceMemberRole
) -> WorkspaceMemberResponse:
    """更新成员角色。"""
    for m in _workspace_members.values():
        if m["workspace_id"] == ws_id and m["user_id"] == user_id:
            m["role"] = role
            return WorkspaceMemberResponse(**m)

    raise KeyError(f"成员不存在: ws={ws_id}, user={user_id}")


# ── 配置管理 ──────────────────────────────────────────────────────────────

def update_config(ws_id: str, data: WorkspaceConfigUpdate) -> WorkspaceConfigResponse:
    """更新工作区配置键值对。"""
    ws = _workspaces.get(ws_id)
    if ws is None or ws["is_deleted"]:
        raise KeyError(f"工作区不存在: {ws_id}")

    now = _now_utc()
    if ws_id not in _workspace_configs:
        _workspace_configs[ws_id] = {}

    _workspace_configs[ws_id][data.key] = {
        "key": data.key,
        "value": data.value,
        "updated_at": now,
    }
    return WorkspaceConfigResponse(
        key=data.key, value=data.value, updated_at=now
    )


def get_config(ws_id: str, key: str) -> WorkspaceConfigResponse | None:
    """获取单个工作区配置。"""
    configs = _workspace_configs.get(ws_id, {})
    cfg = configs.get(key)
    if cfg is None:
        return None
    return WorkspaceConfigResponse(**cfg)


def list_configs(ws_id: str) -> list[WorkspaceConfigResponse]:
    """列出工作区所有配置。"""
    configs = _workspace_configs.get(ws_id, {})
    return [WorkspaceConfigResponse(**cfg) for cfg in configs.values()]
