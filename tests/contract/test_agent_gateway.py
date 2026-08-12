"""Tests for Agent Runtime Gateway - P5."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_agent_runtime_exists():
    assert (SIDECAR_DIR / "ibreeze" / "runtime" / "__init__.py").exists()


def test_agent_runtime_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "runtime" / "__init__.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "start" in content
    assert "cancel" in content
    assert "get_status" in content
    assert "probe_agent" in content
    assert "RuntimeExecutionService" in content
