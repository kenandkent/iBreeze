"""Tests for Sidecar infrastructure and local persistence - P3."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SIDECAR_DIR = ROOT / "sidecar"


def test_rpc_server_exists():
    assert (SIDECAR_DIR / "ibreeze" / "rpc_server.py").exists()


def test_local_db_deleted():
    """local_db.py has been deleted as part of single-writer refactoring.
    All DB access now goes through WriteQueue/UnitOfWork."""
    assert not (SIDECAR_DIR / "ibreeze" / "local_db.py").exists()


def test_company_exists():
    assert (SIDECAR_DIR / "ibreeze" / "company.py").exists()


def test_rpc_server_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "rpc_server.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class RPCServer" in content


def test_production_rpc_server_exists():
    """New production RPC server (replaces old rpc_server.py)."""
    production_path = SIDECAR_DIR / "ibreeze" / "rpc" / "production_server.py"
    assert production_path.exists()
    content = production_path.read_text()
    assert "class ProductionRpcServer" in content


def test_company_is_valid():
    init_path = SIDECAR_DIR / "ibreeze" / "company.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "def create_company" in content
    assert "def list_companies" in content
    assert "def get_company" in content
