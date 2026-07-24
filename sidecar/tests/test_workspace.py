"""Workspace path authorization tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ibreeze.workspace import WorkspaceBoundary


def test_workspace_allows_relative_read_and_write(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    workspace.mkdir()
    source = workspace / "src"
    source.mkdir()
    file = source / "main.py"
    file.write_text("print('ok')", encoding="utf-8")
    boundary = WorkspaceBoundary(workspace)
    assert boundary.resolve_workspace_path(
        "src/main.py",
        for_write=False,
    ) == file
    assert boundary.resolve_workspace_path(
        "src/new.py",
        for_write=True,
    ) == source / "new.py"


@pytest.mark.parametrize(
    "path",
    ["../secret", "/tmp/secret"],
)
def test_workspace_rejects_lexical_escape(
    tmp_path: Path,
    path: str,
) -> None:
    workspace = tmp_path / "run"
    workspace.mkdir()
    boundary = WorkspaceBoundary(workspace)
    with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
        boundary.resolve_workspace_path(path, for_write=True)


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    boundary = WorkspaceBoundary(workspace)
    with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
        boundary.resolve_workspace_path("link/secret.txt", for_write=False)
    with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
        boundary.resolve_workspace_path("link/new.txt", for_write=True)


def test_external_paths_are_read_only_and_explicit(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "run"
    external = tmp_path / "external"
    other = tmp_path / "other"
    for directory in (workspace, external, other):
        directory.mkdir()
    allowed = external / "input.txt"
    allowed.write_text("input", encoding="utf-8")
    denied = other / "input.txt"
    denied.write_text("input", encoding="utf-8")
    boundary = WorkspaceBoundary(
        workspace,
        external_read_roots=(external,),
    )
    assert boundary.resolve_external_read(allowed) == allowed
    with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
        boundary.resolve_external_read(denied)
    with pytest.raises(ValueError, match="HUMAN_APPROVAL_REQUIRED"):
        boundary.authorize_external_write(allowed)
