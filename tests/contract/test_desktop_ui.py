"""Tests for Desktop React UI - P9.
验证前端不再有 mock 实现，所有 hook 均通过 Tauri IPC 调用真实后端。
"""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DESKTOP_DIR = ROOT / "apps" / "desktop"


def test_types_exists():
    assert (DESKTOP_DIR / "src" / "types" / "index.ts").exists()


def test_hooks_conversations_exists():
    assert (DESKTOP_DIR / "src" / "hooks" / "useConversations.ts").exists()


def test_hooks_tasks_exists():
    assert (DESKTOP_DIR / "src" / "hooks" / "useTasks.ts").exists()


def test_types_is_valid():
    content = (DESKTOP_DIR / "src" / "types" / "index.ts").read_text()
    assert "export interface Company" in content
    assert "export interface Conversation" in content
    assert "export interface Message" in content
    assert "export interface AuthResult" in content


def test_hooks_conversations_is_valid():
    content = (DESKTOP_DIR / "src" / "hooks" / "useConversations.ts").read_text()
    assert "export function useConversations" in content
    assert "export function useMessages" in content
    assert "invoke" in content, "useConversations must use Tauri IPC invoke"


def test_login_page_no_mock():
    """LoginPage 不应包含 mock-token 或 mock 实现。"""
    content = (DESKTOP_DIR / "src" / "pages" / "LoginPage.tsx").read_text()
    assert "mock-token" not in content, "LoginPage still contains mock-token"
    assert "invoke" in content, "LoginPage must use Tauri IPC invoke"
    assert "login" in content.lower()


def test_register_page_no_mock():
    """RegisterPage 不应包含模拟跳转，必须调用真实 IPC。"""
    content = (DESKTOP_DIR / "src" / "pages" / "RegisterPage.tsx").read_text()
    assert "模拟" not in content, "RegisterPage still contains 模拟"
    assert "invoke" in content, "RegisterPage must use Tauri IPC invoke"
    assert "register" in content.lower()


def test_hooks_use_company_uses_invoke():
    content = (DESKTOP_DIR / "src" / "hooks" / "useCompany.ts").read_text()
    assert "invoke" in content, "useCompany must use Tauri IPC invoke"
    assert "TODO" not in content, "useCompany still has TODO"


def test_hooks_use_conversation_uses_invoke():
    content = (DESKTOP_DIR / "src" / "hooks" / "useConversation.ts").read_text()
    assert "invoke" in content, "useConversation must use Tauri IPC invoke"
    assert "TODO" not in content, "useConversation still has TODO"


def test_hooks_use_knowledge_uses_invoke():
    content = (DESKTOP_DIR / "src" / "hooks" / "useKnowledge.ts").read_text()
    assert "invoke" in content, "useKnowledge must use Tauri IPC invoke"
    assert "TODO" not in content, "useKnowledge still has TODO"


def test_hooks_use_workspace_uses_invoke():
    content = (DESKTOP_DIR / "src" / "hooks" / "useWorkspace.ts").read_text()
    assert "invoke" in content, "useWorkspace must use Tauri IPC invoke"
    assert "TODO" not in content, "useWorkspace still has TODO"


def test_hooks_use_orchestration_uses_invoke():
    content = (DESKTOP_DIR / "src" / "hooks" / "useOrchestration.ts").read_text()
    assert "invoke" in content, "useOrchestration must use Tauri IPC invoke"
    assert "TODO" not in content, "useOrchestration still has TODO"


def test_hooks_use_agent_uses_invoke():
    content = (DESKTOP_DIR / "src" / "hooks" / "useAgent.ts").read_text()
    assert "invoke" in content, "useAgent must use Tauri IPC invoke"
    assert "TODO" not in content, "useAgent still has TODO"


def test_no_mock_token_anywhere():
    """整个 desktop/src 目录不应包含 mock-token。"""
    src_dir = DESKTOP_DIR / "src"
    for f in src_dir.rglob("*.tsx"):
        content = f.read_text()
        assert "mock-token" not in content, f"{f.name} still contains mock-token"
    for f in src_dir.rglob("*.ts"):
        content = f.read_text()
        assert "mock-token" not in content, f"{f.name} still contains mock-token"
