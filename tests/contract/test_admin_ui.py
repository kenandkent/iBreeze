"""Tests for Admin Web React UI - P10.
验证管理后台不再有 mock 常量，SettingsPage 对接真实 API。
"""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
ADMIN_DIR = ROOT / "apps" / "admin-web"


def test_types_exists():
    assert (ADMIN_DIR / "src" / "types" / "index.ts").exists()


def test_types_is_valid():
    content = (ADMIN_DIR / "src" / "types" / "index.ts").read_text()
    assert "export interface User" in content
    assert "export interface Skill" in content
    assert "export interface CatalogRelease" in content
    assert "export interface AuditLog" in content


def test_settings_page_no_mock():
    """SettingsPage 不应包含 MOCK_SETTINGS 常量。"""
    content = (ADMIN_DIR / "src" / "pages" / "SettingsPage.tsx").read_text()
    assert "MOCK_SETTINGS" not in content, "SettingsPage still contains MOCK_SETTINGS"
    assert "fetch" in content or "useQuery" in content, "SettingsPage must use real API call"


def test_vite_config_has_proxy():
    """vite.config.ts 必须配置 API 代理到后端。"""
    content = (ADMIN_DIR / "vite.config.ts").read_text()
    assert "proxy" in content, "vite.config.ts must have proxy configuration"
    assert "51080" in content, "proxy must target port 51080"
