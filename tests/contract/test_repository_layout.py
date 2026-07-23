"""Tests for repository layout existence - P0-T01."""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent


def test_desktop_package_json():
    assert (ROOT / "apps" / "desktop" / "package.json").exists()


def test_desktop_tsconfig():
    assert (ROOT / "apps" / "desktop" / "tsconfig.json").exists()


def test_desktop_vite_config():
    assert (ROOT / "apps" / "desktop" / "vite.config.ts").exists()


def test_admin_web_package_json():
    assert (ROOT / "apps" / "admin-web" / "package.json").exists()


def test_admin_web_tsconfig():
    assert (ROOT / "apps" / "admin-web" / "tsconfig.json").exists()


def test_admin_web_vite_config():
    assert (ROOT / "apps" / "admin-web" / "vite.config.ts").exists()


def test_desktop_core_cargo_toml():
    assert (ROOT / "apps" / "desktop-core" / "Cargo.toml").exists()


def test_desktop_core_main_rs():
    assert (ROOT / "apps" / "desktop-core" / "src" / "main.rs").exists()


def test_desktop_core_lib_rs():
    assert (ROOT / "apps" / "desktop-core" / "src" / "lib.rs").exists()


def test_sidecar_pyproject():
    assert (ROOT / "sidecar" / "pyproject.toml").exists()


def test_sidecar_main():
    assert (ROOT / "sidecar" / "ibreeze" / "main.py").exists()


def test_backend_api_pyproject():
    assert (ROOT / "apps" / "backend-api" / "pyproject.toml").exists()


def test_backend_api_main():
    assert (ROOT / "apps" / "backend-api" / "src" / "ibreeze_backend" / "main.py").exists()


def test_e2e_package_json():
    assert (ROOT / "tests" / "e2e" / "package.json").exists()


def test_e2e_playwright_config():
    assert (ROOT / "tests" / "e2e" / "playwright.config.ts").exists()


def test_gitignore():
    assert (ROOT / ".gitignore").exists()


def test_coverage_exclusions():
    assert (ROOT / "coverage-exclusions.yml").exists()


def test_verify_all_script():
    assert (ROOT / "scripts" / "verify-all.sh").exists()


def test_readme():
    assert (ROOT / "README.md").exists()


def test_deploy_doc():
    assert (ROOT / "docs" / "部署文档.md").exists()


def test_sidecar_init():
    assert (ROOT / "sidecar" / "ibreeze" / "__init__.py").exists()


def test_backend_api_init():
    assert (ROOT / "apps" / "backend-api" / "src" / "ibreeze_backend" / "__init__.py").exists()
