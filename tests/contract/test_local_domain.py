"""Tests for local conversation and task domain - P4."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_conversation_exists():
    assert (SIDECAR_DIR / "ibreeze" / "conversation.py").exists()


def test_conversation_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "conversation.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def create_conversation" in content
    assert "def add_message" in content
    assert "def list_messages" in content
    assert "def archive_conversation" in content
    assert "def search_conversations" in content
