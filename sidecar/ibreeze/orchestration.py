"""编排管理领域服务。

提供编排 CRUD、节点管理、边（数据流）管理、编排版本控制、
编排运行记录管理能力。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    OrchestrationCreate,
    OrchestrationEdgeCreate,
    OrchestrationEdgeResponse,
    OrchestrationNodeCreate,
    OrchestrationNodeResponse,
    OrchestrationNodeType,
    OrchestrationResponse,
    OrchestrationRunResponse,
    OrchestrationRunStatus,
    OrchestrationStatus,
    OrchestrationUpdate,
)


# ── 内存存储 ──────────────────────────────────────────────────────────────

_orchestrations: dict[str, dict[str, Any]] = {}
_orchestration_nodes: dict[str, dict[str, Any]] = {}
_orchestration_edges: dict[str, dict[str, Any]] = {}
_orchestration_runs: dict[str, dict[str, Any]] = {}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── 编排 CRUD ─────────────────────────────────────────────────────────────

def create_orchestration(
    company_id: str,
    name: str,
    description: str | None = None,
    nodes: list[OrchestrationNodeCreate] | None = None,
    edges: list[OrchestrationEdgeCreate] | None = None,
) -> OrchestrationResponse:
    """创建编排，自动设置版本号为 1。"""
    import uuid

    orc_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": orc_id,
        "company_id": company_id,
        "name": name,
        "description": description,
        "status": OrchestrationStatus.DRAFT,
        "version": 1,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _orchestrations[orc_id] = record

    # 创建初始节点
    created_nodes: list[OrchestrationNodeResponse] = []
    node_id_map: dict[int, str] = {}  # 索引 -> 节点 ID

    if nodes:
        for idx, node_data in enumerate(nodes):
            node_id = str(uuid.uuid4())
            node_record: dict[str, Any] = {
                "id": node_id,
                "orchestration_id": orc_id,
                "name": node_data.name,
                "node_type": node_data.node_type,
                "config": node_data.config,
                "created_at": now,
            }
            _orchestration_nodes[node_id] = node_record
            node_id_map[idx] = node_id
            created_nodes.append(OrchestrationNodeResponse(**node_record))

    # 创建初始边
    created_edges: list[OrchestrationEdgeResponse] = []
    if edges:
        for edge_data in edges:
            edge_id = str(uuid.uuid4())
            edge_record: dict[str, Any] = {
                "id": edge_id,
                "orchestration_id": orc_id,
                "source_node_id": edge_data.source_node_id,
                "target_node_id": edge_data.target_node_id,
                "created_at": now,
            }
            _orchestration_edges[edge_id] = edge_record
            created_edges.append(OrchestrationEdgeResponse(**edge_record))

    return OrchestrationResponse(
        **record, nodes=created_nodes, edges=created_edges
    )


def list_orchestrations(
    company_id: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> list[OrchestrationResponse]:
    """分页列出编排，可按企业 ID 过滤。"""
    active = [
        o
        for o in _orchestrations.values()
        if not o["is_deleted"] and (company_id is None or o["company_id"] == company_id)
    ]
    return [OrchestrationResponse(**o) for o in active[offset : offset + limit]]


def get_orchestration(orc_id: str) -> OrchestrationResponse:
    """获取单个编排详情（含节点和边）。"""
    record = _orchestrations.get(orc_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    nodes = [
        OrchestrationNodeResponse(**n)
        for n in _orchestration_nodes.values()
        if n["orchestration_id"] == orc_id
    ]
    edges = [
        OrchestrationEdgeResponse(**e)
        for e in _orchestration_edges.values()
        if e["orchestration_id"] == orc_id
    ]

    return OrchestrationResponse(**record, nodes=nodes, edges=edges)


def update_orchestration(orc_id: str, data: OrchestrationUpdate) -> OrchestrationResponse:
    """更新编排，自动递增版本号。"""
    record = _orchestrations.get(orc_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        record[key] = value

    record["version"] += 1
    record["updated_at"] = _now_utc()

    nodes = [
        OrchestrationNodeResponse(**n)
        for n in _orchestration_nodes.values()
        if n["orchestration_id"] == orc_id
    ]
    edges = [
        OrchestrationEdgeResponse(**e)
        for e in _orchestration_edges.values()
        if e["orchestration_id"] == orc_id
    ]

    return OrchestrationResponse(**record, nodes=nodes, edges=edges)


def delete_orchestration(orc_id: str) -> None:
    """软删除编排。"""
    record = _orchestrations.get(orc_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")
    record["is_deleted"] = True
    record["updated_at"] = _now_utc()


# ── 节点管理 ──────────────────────────────────────────────────────────────

def add_node(orc_id: str, data: OrchestrationNodeCreate) -> OrchestrationNodeResponse:
    """向编排添加节点。"""
    orc = _orchestrations.get(orc_id)
    if orc is None or orc["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    import uuid

    node_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": node_id,
        "orchestration_id": orc_id,
        "name": data.name,
        "node_type": data.node_type,
        "config": data.config,
        "created_at": now,
    }
    _orchestration_nodes[node_id] = record
    orc["version"] += 1
    orc["updated_at"] = now

    return OrchestrationNodeResponse(**record)


def remove_node(orc_id: str, node_id: str) -> None:
    """移除节点及其关联的所有边。"""
    orc = _orchestrations.get(orc_id)
    if orc is None or orc["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    node = _orchestration_nodes.get(node_id)
    if node is None or node["orchestration_id"] != orc_id:
        raise KeyError(f"节点不存在: {node_id}")

    del _orchestration_nodes[node_id]

    # 移除关联边
    edges_to_remove = [
        eid
        for eid, e in _orchestration_edges.items()
        if e["orchestration_id"] == orc_id
        and (e["source_node_id"] == node_id or e["target_node_id"] == node_id)
    ]
    for eid in edges_to_remove:
        del _orchestration_edges[eid]

    orc["version"] += 1
    orc["updated_at"] = _now_utc()


# ── 边管理 ────────────────────────────────────────────────────────────────

def add_edge(orc_id: str, data: OrchestrationEdgeCreate) -> OrchestrationEdgeResponse:
    """向编排添加边（数据流）。"""
    orc = _orchestrations.get(orc_id)
    if orc is None or orc["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    # 校验节点存在且属于本编排
    source = _orchestration_nodes.get(data.source_node_id)
    target = _orchestration_nodes.get(data.target_node_id)
    if source is None or source["orchestration_id"] != orc_id:
        raise KeyError(f"源节点不存在: {data.source_node_id}")
    if target is None or target["orchestration_id"] != orc_id:
        raise KeyError(f"目标节点不存在: {data.target_node_id}")

    if data.source_node_id == data.target_node_id:
        raise ValueError("不允许自环边")

    import uuid

    edge_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": edge_id,
        "orchestration_id": orc_id,
        "source_node_id": data.source_node_id,
        "target_node_id": data.target_node_id,
        "created_at": now,
    }
    _orchestration_edges[edge_id] = record
    orc["version"] += 1
    orc["updated_at"] = now

    return OrchestrationEdgeResponse(**record)


# ── 运行管理 ──────────────────────────────────────────────────────────────

def run_orchestration(orc_id: str) -> OrchestrationRunResponse:
    """触发编排运行，创建运行记录。"""
    orc = _orchestrations.get(orc_id)
    if orc is None or orc["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    import uuid

    run_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": run_id,
        "orchestration_id": orc_id,
        "orchestration_version": orc["version"],
        "status": OrchestrationRunStatus.PENDING,
        "started_at": now,
        "completed_at": None,
        "result": None,
        "error": None,
    }
    _orchestration_runs[run_id] = record

    orc["updated_at"] = now
    return OrchestrationRunResponse(**record)


def get_run_history(orc_id: str) -> list[OrchestrationRunResponse]:
    """获取编排的运行历史。"""
    orc = _orchestrations.get(orc_id)
    if orc is None or orc["is_deleted"]:
        raise KeyError(f"编排不存在: {orc_id}")

    runs = sorted(
        [
            r
            for r in _orchestration_runs.values()
            if r["orchestration_id"] == orc_id
        ],
        key=lambda r: r["started_at"],
        reverse=True,
    )
    return [OrchestrationRunResponse(**r) for r in runs]
