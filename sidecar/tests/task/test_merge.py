"""test_merge：Git 安全红线（用户主工作区不被触碰 / 机械合并零 Agent / 冲突分类）。"""

from __future__ import annotations

import os
import subprocess

import pytest

from acos.task.merge import ArtifactManifestMerge, GitMergeStrategy, GitSafetyError


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True)


def _init_repo(tmp_path):
    repo = str(tmp_path / "repo")
    os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    with open(os.path.join(repo, "base.txt"), "w") as f:
        f.write("base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


@pytest.mark.asyncio
async def test_add_worktree_derives_from_baseline_not_user_tree(tmp_path):
    repo = _init_repo(tmp_path)
    strat = GitMergeStrategy(repo, "task-m1")
    baseline = strat.baseline_commit()
    wt = strat.add_worktree("n1", baseline)
    # 用户主工作树不应新建文件（除 .git 内部）
    top = set(os.listdir(repo))
    assert "acos_worktrees" not in top  # worktree 放在 .git 内部
    # 基线 commit 不变
    assert strat.baseline_commit() == baseline
    # worktree 内可独立提交而不影响主树 HEAD
    with open(os.path.join(wt, "wt_file.txt"), "w") as f:
        f.write("from worktree\n")
    _git(wt, "add", ".")
    _git(wt, "commit", "-q", "-m", "wt change")
    assert strat.baseline_commit() == baseline  # 主树未动


@pytest.mark.asyncio
async def test_worktree_rejected_when_user_tree_dirty(tmp_path):
    repo = _init_repo(tmp_path)
    strat = GitMergeStrategy(repo, "task-m2")
    baseline = strat.baseline_commit()
    # 制造未提交改动
    with open(os.path.join(repo, "dirty.txt"), "w") as f:
        f.write("x\n")
    with pytest.raises(GitSafetyError):
        strat.add_worktree("n1", baseline)


@pytest.mark.asyncio
async def test_mechanical_merge_success_no_user_touch(tmp_path):
    repo = _init_repo(tmp_path)
    strat = GitMergeStrategy(repo, "task-m3")
    baseline = strat.baseline_commit()
    wt = strat.add_worktree("n1", baseline)
    # 在 worktree 制造改动并提交（作为 other_branch）
    with open(os.path.join(wt, "wt_file.txt"), "w") as f:
        f.write("hello\n")
    _git(wt, "add", ".")
    _git(wt, "commit", "-q", "-m", "wt change")
    other = strat.branch_name("n1")
    # 机械合并（零 Agent 调用）应成功
    res = strat.mechanical_merge(wt, other, baseline)
    assert res.merged is True
    assert res.conflict_type is None
    assert res.integration_commit is not None
    # 用户主树 HEAD 仍指向基线
    assert strat.baseline_commit() == baseline


@pytest.mark.asyncio
async def test_mechanical_merge_conflict_classified(tmp_path):
    repo = _init_repo(tmp_path)
    strat = GitMergeStrategy(repo, "task-m4")
    baseline = strat.baseline_commit()
    wt = strat.add_worktree("n1", baseline)
    # 主树在 base.txt 同一行改动，worktree 也改同一文件 -> 冲突
    with open(os.path.join(repo, "base.txt"), "w") as f:
        f.write("main change\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "main change")
    # 注意：user tree 已提交（非 dirty），安全；但合并会与 main 冲突
    with open(os.path.join(wt, "base.txt"), "w") as f:
        f.write("wt change\n")
    _git(wt, "add", ".")
    _git(wt, "commit", "-q", "-m", "wt change")
    main_head = subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    res = strat.mechanical_merge(wt, main_head, baseline)  # worktree 合并 main HEAD
    assert res.merged is False
    assert res.conflict_type == "ResourceConflict"


@pytest.mark.asyncio
async def test_cleanup_only_removes_own_worktree(tmp_path):
    repo = _init_repo(tmp_path)
    strat = GitMergeStrategy(repo, "task-m5")
    baseline = strat.baseline_commit()
    wt = strat.add_worktree("n1", baseline)
    # 用户主树另有自己分支
    _git(repo, "branch", "user-branch")
    strat.cleanup("n1", wt)
    branches = subprocess.run(["git", "-C", repo, "branch"], capture_output=True, text=True).stdout
    assert "user-branch" in branches  # 用户分支保留
    assert strat.branch_name("n1").split("/")[-1] not in branches  # 本任务分支已删


@pytest.mark.asyncio
async def test_artifact_manifest_merge_conflict(tmp_path):
    # 无重叠 -> 合并成功
    ok = ArtifactManifestMerge.merge([
        {"a.txt": "h1"}, {"b.txt": "h2"},
    ])
    assert ok.merged is True
    # 重叠且 hash 不一致 -> ResourceConflict
    bad = ArtifactManifestMerge.merge([
        {"a.txt": "h1"}, {"a.txt": "h2"},
    ])
    assert bad.merged is False
    assert bad.conflict_type == "ResourceConflict"
