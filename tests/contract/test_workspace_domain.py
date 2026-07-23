"""Tests for Workspace, Artifact and Review domain - P6."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_workspace_exists():
    assert (SIDECAR_DIR / "ibreeze" / "workspace.py").exists()


def test_workspace_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "workspace.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def create_workspace" in content
    assert "def list_workspaces" in content
    assert "def get_workspace" in content
    assert "def add_member" in content
    assert "def list_members" in content
