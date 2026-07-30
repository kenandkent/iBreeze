"""Tests for Workspace, Artifact and Review domain - P6."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_workspace_exists():
    assert (SIDECAR_DIR / "ibreeze" / "workspace" / "__init__.py").exists()


def test_workspace_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "workspace" / "__init__.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "create_workspace" in content
    assert "get_workspace" in content
    assert "apply_workspace" in content
    assert "abandon_workspace" in content
    assert "create_bundle" in content
