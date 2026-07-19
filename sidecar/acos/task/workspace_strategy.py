"""Workspace 类型选择（P9-T5）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkspaceInstance:
    strategy: str
    root: str
    read_only: bool = False


class WorkspaceStrategy:
    """按任务性质选择 Workspace 类型（不强制所有节点都用 Git Worktree）。"""

    @staticmethod
    def for_node(node_type: str, workspace_strategy: Optional[str], base_root: str,
                 task_id: str, node_id: str) -> WorkspaceInstance:
        if workspace_strategy == "GitWorktree":
            return WorkspaceInstance(strategy="GitWorktree", root=base_root, read_only=False)
        if workspace_strategy == "ReadOnly":
            return WorkspaceInstance(strategy="ReadOnly", root=base_root, read_only=True)
        if workspace_strategy == "Restricted":
            return WorkspaceInstance(strategy="Restricted", root=base_root, read_only=False)
        # 默认：通用文件/产出类 -> TaskWorkspace（隔离目录）
        return WorkspaceInstance(strategy="TaskWorkspace", root=base_root, read_only=False)
