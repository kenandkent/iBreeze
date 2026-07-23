"""Tests for Agent Runtime Gateway - P5."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_agent_runtime_exists():
    assert (SIDECAR_DIR / "ibreeze" / "agent_runtime.py").exists()


def test_agent_runtime_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "agent_runtime.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def register_agent" in content
    assert "def list_agents" in content
    assert "def get_agent_status" in content
    assert "def run_agent" in content
    assert "def stop_agent" in content
