"""Tests for REST middleware, idempotency and audit - P1-T07."""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
BACKEND_DIR = ROOT / "apps" / "backend-api"


def test_audit_log_model_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "audit_log.py").exists()


def test_idempotency_key_model_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "idempotency_key.py").exists()


def test_audit_middleware_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "middleware" / "audit.py").exists()


def test_idempotency_middleware_exists():
    assert (BACKEND_DIR / "src" / "ibreeze_backend" / "middleware" / "idempotency.py").exists()


def test_audit_log_model_is_valid():
    """Verify audit_log model compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "audit_log.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class AuditLog" in content
    assert "action" in content
    assert "resource_type" in content


def test_idempotency_key_model_is_valid():
    """Verify idempotency_key model compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "models" / "idempotency_key.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class IdempotencyKey" in content
    assert "key" in content
    assert "expires_at" in content


def test_audit_middleware_is_valid():
    """Verify audit middleware compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "middleware" / "audit.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class AuditMiddleware" in content


def test_idempotency_middleware_is_valid():
    """Verify idempotency middleware compiles."""
    init_path = BACKEND_DIR / "src" / "ibreeze_backend" / "middleware" / "idempotency.py"
    content = init_path.read_text()
    compile(content, str(init_path), "exec")
    assert "class IdempotencyMiddleware" in content
