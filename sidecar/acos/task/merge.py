"""合并与修复策略（P9-T7，含 Git 安全规则）。

Git 类任务必须遵守一组安全规则：**绝不触碰用户已有工作区**。
- 创建 Worktree 前先记录不可变基线 commit
- `git worktree add` 从基线派生，绝不对用户主工作目录执行 reset/checkout
- 存在未提交改动导致无法安全创建 Worktree -> 转人工（不强行绕过）
- 机械合并零 Agent 调用（直接 Git 命令）
- 清理只删本任务创建的 Worktree/分支
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from typing import Optional


class GitSafetyError(Exception):
    pass


@dataclass
class MergeResult:
    merged: bool
    conflict_type: Optional[str] = None  # ResourceConflict / DecisionConflict / VersionConflict
    integration_commit: Optional[str] = None
    baseline_commit: Optional[str] = None
    diff_sha256: Optional[str] = None
    patch_path: Optional[str] = None
    bundle_path: Optional[str] = None
    message: str = ""


class GitMergeStrategy:
    """Git 类任务机械合并（零 Agent 调用）。"""

    def __init__(self, repo_root: str, task_id: str) -> None:
        self._repo = repo_root
        self._task_id = task_id

    def _run(self, *args: str, check: bool = True) -> str:
        res = subprocess.run(
            ["git", "-C", self._repo, *args],
            capture_output=True, text=True,
        )
        if check and res.returncode != 0:
            raise GitSafetyError(res.stderr.strip() or f"git {' '.join(args)} 失败")
        return res.stdout.strip()

    def baseline_commit(self) -> str:
        """记录不可变基线 commit 引用。"""
        return self._run("rev-parse", "HEAD")

    def branch_name(self, node_id: str) -> str:
        return f"acos/task/{self._task_id}/{node_id}"

    def add_worktree(self, node_id: str, baseline_commit: str) -> str:
        """从基线 commit 派生 Worktree。

        若用户主工作目录存在未提交改动导致无法安全创建，转人工（抛 GitSafetyError）。
        """
        # 安全检查：用户主工作树是否有未提交改动
        status = self._run("status", "--porcelain", check=False)
        if status.strip():
            raise GitSafetyError(
                "用户主工作目录存在未提交改动，拒绝创建 Worktree 以防破坏"
            )
        wt_path = os.path.join(self._repo, ".git", "acos_worktrees",
                               f"{self._task_id}_{node_id}")
        os.makedirs(os.path.dirname(wt_path), exist_ok=True)
        branch = self.branch_name(node_id)
        # 从基线 commit 派生（不触碰用户工作树）
        self._run("worktree", "add", "--force", "-b", branch, wt_path, baseline_commit)
        return wt_path

    def mechanical_merge(
        self, wt_path: str, other_branch: str, baseline_commit: str,
    ) -> MergeResult:
        """机械合并（无重叠改动直接合并；重叠 -> ResourceConflict）。"""
        baseline = baseline_commit
        # 检查与 other_branch 是否在相同文件有重叠改动
        try:
            out = subprocess.run(
                ["git", "-C", wt_path, "merge", "--no-commit", "--no-ff", other_branch],
                capture_output=True, text=True,
            )
        except Exception as exc:  # pragma: no cover
            raise GitSafetyError(str(exc))
        if out.returncode != 0:
            # 冲突：分类为 Resource Conflict（同文件重叠）
            subprocess.run(["git", "-C", wt_path, "merge", "--abort"],
                           capture_output=True, text=True)
            diff_sha = self._diff_sha(wt_path, baseline, other_branch)
            return MergeResult(
                merged=False, conflict_type="ResourceConflict",
                baseline_commit=baseline, diff_sha256=diff_sha,
                message="文件重叠冲突，交 Manager 生成合并计划",
            )
        # 成功：提交 integration
        self._run_cwd(wt_path, "commit", "-m",
                      f"acos merge: task {self._task_id}", check=False)
        commit = self._run_cwd(wt_path, "rev-parse", "HEAD")
        diff_sha = self._diff_sha(wt_path, baseline, commit)
        return MergeResult(
            merged=True, integration_commit=commit, baseline_commit=baseline,
            diff_sha256=diff_sha,
            message="机械合并完成（零 Agent 调用）",
        )

    def _run_cwd(self, cwd: str, *args: str, check: bool = True) -> str:
        res = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
        if check and res.returncode != 0:
            raise GitSafetyError(res.stderr.strip() or f"git {' '.join(args)} 失败")
        return res.stdout.strip()

    def _diff_sha(self, cwd: str, a: str, b: str) -> str:
        out = self._run_cwd(cwd, "diff", a, b, check=False)
        return hashlib.sha256(out.encode()).hexdigest()

    def cleanup(self, node_id: str, wt_path: str) -> None:
        """清理只删除本任务创建的 Worktree 与临时分支，不触碰用户原有工作区。"""
        branch = self.branch_name(node_id)
        subprocess.run(["git", "-C", self._repo, "worktree", "remove", wt_path, "--force"],
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", self._repo, "branch", "-D", branch],
                       capture_output=True, text=True)


class ArtifactManifestMerge:
    """通用文件/产出类任务合并：比对 artifact manifest，无重叠直接合并。"""

    @staticmethod
    def merge(manifests: list[dict]) -> MergeResult:
        """manifests: 各节点的 {path: hash}。有重叠路径且 hash 不一致 -> ResourceConflict。"""
        merged: dict[str, str] = {}
        for m in manifests:
            for path, h in m.items():
                if path in merged and merged[path] != h:
                    return MergeResult(
                        merged=False, conflict_type="ResourceConflict",
                        message=f"路径 {path} 在多个节点产出不一致，交 Manager 裁决",
                    )
                merged[path] = h
        return MergeResult(merged=True, message="artifact manifest 合并完成（无 Git 调用）")
