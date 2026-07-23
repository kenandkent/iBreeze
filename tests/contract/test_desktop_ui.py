"""Tests for Desktop React UI - P9."""
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


def test_components_sidebar_exists():
    assert (DESKTOP_DIR / "src" / "components" / "Sidebar.tsx").exists()


def test_components_chat_panel_exists():
    assert (DESKTOP_DIR / "src" / "components" / "ChatPanel.tsx").exists()


def test_components_task_list_exists():
    assert (DESKTOP_DIR / "src" / "components" / "TaskList.tsx").exists()


def test_types_is_valid():
    content = (DESKTOP_DIR / "src" / "types" / "index.ts").read_text()
    assert "export interface Company" in content
    assert "export interface Conversation" in content
    assert "export interface Message" in content
    assert "export interface Task" in content


def test_hooks_is_valid():
    content = (DESKTOP_DIR / "src" / "hooks" / "useConversations.ts").read_text()
    assert "export function useConversations" in content
    assert "export function useMessages" in content
    assert "export function useSendMessage" in content


def test_task_hooks_is_valid():
    content = (DESKTOP_DIR / "src" / "hooks" / "useTasks.ts").read_text()
    assert "export function useTasks" in content
    assert "export function useCreateTask" in content
