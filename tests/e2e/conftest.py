"""Shared fixtures for E2E tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_backend_root = Path(__file__).resolve().parents[2] / "apps" / "backend-api" / "src"
_sidecar_root = Path(__file__).resolve().parents[2] / "sidecar"
for _p in (_backend_root, _sidecar_root):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)


@pytest.fixture
def app():
    """Import and return the FastAPI application."""
    from ibreeze_backend.main import app as fastapi_app
    return fastapi_app
