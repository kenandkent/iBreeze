"""Tests for sidecar assets packaging - P0-T04."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
ASSETS_DIR = ROOT / "sidecar" / "ibreeze" / "assets"
MANIFEST_PATH = ASSETS_DIR / "manifest.json"
MANIFEST_SCHEMA_PATH = ASSETS_DIR / "manifest.schema.json"


def test_assets_package_exists():
    assert ASSETS_DIR.exists()
    assert (ASSETS_DIR / "__init__.py").exists()


def test_manifest_exists():
    assert MANIFEST_PATH.exists()


def test_manifest_schema_exists():
    assert MANIFEST_SCHEMA_PATH.exists()


def test_manifest_valid_json():
    with open(MANIFEST_PATH) as f:
        data = json.load(f)
    assert "version" in data
    assert "assets" in data
    assert isinstance(data["assets"], list)


def test_manifest_has_version():
    with open(MANIFEST_PATH) as f:
        data = json.load(f)
    assert isinstance(data["version"], str)
    assert len(data["version"]) > 0


def test_assets_init_importable():
    """Verify the assets __init__.py is valid Python."""
    init_path = ASSETS_DIR / "__init__.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
