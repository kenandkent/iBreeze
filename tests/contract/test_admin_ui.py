"""Tests for Admin Web React UI - P10."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ADMIN_DIR = ROOT / "apps" / "admin-web"


def test_types_exists():
    assert (ADMIN_DIR / "src" / "types" / "index.ts").exists()


def test_components_admin_sidebar_exists():
    assert (ADMIN_DIR / "src" / "components" / "AdminSidebar.tsx").exists()


def test_components_user_list_exists():
    assert (ADMIN_DIR / "src" / "components" / "UserList.tsx").exists()


def test_components_skill_list_exists():
    assert (ADMIN_DIR / "src" / "components" / "SkillList.tsx").exists()


def test_types_is_valid():
    content = (ADMIN_DIR / "src" / "types" / "index.ts").read_text()
    assert "export interface User" in content
    assert "export interface Skill" in content
    assert "export interface CatalogRelease" in content
    assert "export interface AuditLog" in content


def test_admin_sidebar_is_valid():
    content = (ADMIN_DIR / "src" / "components" / "AdminSidebar.tsx").read_text()
    assert "export function AdminSidebar" in content
    assert "Users" in content
    assert "Skills" in content
    assert "Catalog" in content


def test_user_list_is_valid():
    content = (ADMIN_DIR / "src" / "components" / "UserList.tsx").read_text()
    assert "export function UserList" in content
    assert "username" in content
    assert "email" in content
    assert "role" in content
