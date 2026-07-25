"""Tests for all ibreeze.security sub-modules (audit, encryption, path_safety, rbac, redaction, skill_verify)."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── security.audit ────────────────────────────────────────────────────

from ibreeze.security.audit import (
    GENESIS_HASH,
    _compute_hash,
    _get_prev_hash,
    _sanitize,
    list_audit_logs,
    log_audit,
)


def test_sanitize_redacts_sensitive_keys() -> None:
    data = {"password": "secret123", "token": "abc", "normal": "keep"}
    result = _sanitize(data)
    assert result["password"] == "[REDACTED]"
    assert result["token"] == "[REDACTED]"
    assert result["normal"] == "keep"


def test_sanitize_truncates_long_strings() -> None:
    long = "x" * 200
    result = _sanitize({"key": long})
    assert len(result["key"]) < 200
    assert "[truncated" in result["key"]


def test_sanitize_nests_dict() -> None:
    data = {"outer": {"password": "val"}}
    result = _sanitize(data)
    assert result["outer"]["password"] == "[REDACTED]"


def test_sanitize_none_returns_none() -> None:
    assert _sanitize(None) is None


def test_compute_hash_deterministic() -> None:
    h1 = _compute_hash("data", GENESIS_HASH)
    h2 = _compute_hash("data", GENESIS_HASH)
    assert h1 == h2
    assert len(h1) == 64


def test_compute_hash_varies_with_prev() -> None:
    h1 = _compute_hash("data", "a" * 64)
    h2 = _compute_hash("data", "b" * 64)
    assert h1 != h2


@pytest.mark.asyncio
async def test_get_prev_hash_returns_genesis_when_empty() -> None:
    mock_db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone.return_value = None
    mock_db.execute.return_value = cursor
    result = await _get_prev_hash(mock_db, "cid")
    assert result == GENESIS_HASH


@pytest.mark.asyncio
async def test_get_prev_hash_returns_last_hash() -> None:
    mock_db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone.return_value = ("abc123",)
    mock_db.execute.return_value = cursor
    result = await _get_prev_hash(mock_db, "cid")
    assert result == "abc123"


@pytest.mark.asyncio
async def test_log_audit_writes_and_returns_id() -> None:
    mock_db = AsyncMock()
    # For dedup check
    dedup_cursor = AsyncMock()
    dedup_cursor.fetchone.return_value = None
    # For prev hash
    prev_cursor = AsyncMock()
    prev_cursor.fetchone.return_value = None
    mock_db.execute.side_effect = [dedup_cursor, prev_cursor, AsyncMock()]
    result = await log_audit(
        mock_db,
        company_id="c1",
        actor_id="a1",
        actor_type="user",
        action="test.action",
        resource_type="test",
        resource_id="r1",
        detail={"key": "value"},
    )
    assert result  # returns non-empty log_id
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_log_audit_dedup_returns_empty() -> None:
    mock_db = AsyncMock()
    dedup_cursor = AsyncMock()
    dedup_cursor.fetchone.return_value = ("existing-id",)
    mock_db.execute.return_value = dedup_cursor
    result = await log_audit(
        mock_db,
        company_id="c1",
        actor_id=None,
        actor_type="system",
        action="dup.action",
        resource_type="test",
        resource_id="r1",
        trace_id="trace-123",
    )
    assert result == ""


@pytest.mark.asyncio
async def test_list_audit_logs_queries_db() -> None:
    mock_db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchall.return_value = [{"id": "1", "action": "test"}]
    mock_db.execute.return_value = cursor
    result = await list_audit_logs(mock_db, company_id="c1")
    assert len(result) == 1
    assert result[0]["action"] == "test"


@pytest.mark.asyncio
async def test_list_audit_logs_empty() -> None:
    mock_db = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchall.return_value = []
    mock_db.execute.return_value = cursor
    result = await list_audit_logs(mock_db)
    assert result == []


# ── security.encryption ──────────────────────────────────────────────

from ibreeze.security.encryption import (
    derive_key,
    encrypt,
    decrypt,
    hash_password,
    verify_password,
    generate_api_key,
    sha256_hex,
    is_bcrypt_hash,
)


def test_derive_key_returns_key_and_salt() -> None:
    key, salt = derive_key("password123")
    assert isinstance(key, bytes)
    assert isinstance(salt, bytes)
    assert len(salt) == 16


def test_derive_key_deterministic_with_same_salt() -> None:
    _, salt = derive_key("test")
    k1, _ = derive_key("test", salt=salt)
    k2, _ = derive_key("test", salt=salt)
    assert k1 == k2


def test_encrypt_decrypt_roundtrip() -> None:
    key, _ = derive_key("testkey")
    plaintext = "hello world"
    ct = encrypt(plaintext, key)
    assert ct != plaintext
    pt = decrypt(ct, key)
    assert pt == plaintext


def test_hash_and_verify_password() -> None:
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_generate_api_key_length() -> None:
    key = generate_api_key()
    assert isinstance(key, str)
    assert len(key) > 20


def test_sha256_hex() -> None:
    result = sha256_hex(b"hello")
    assert result == hashlib.sha256(b"hello").hexdigest()
    assert len(result) == 64


def test_is_bcrypt_hash() -> None:
    assert is_bcrypt_hash("$2b$10$abcdef")
    assert is_bcrypt_hash("$2a$12$xyz")
    assert not is_bcrypt_hash("$argon2id$...")
    assert not is_bcrypt_hash("plain")


# ── security.path_safety ─────────────────────────────────────────────

from ibreeze.security.path_safety import (
    PathViolationError,
    resolve_safe,
    validate_no_traversal,
    create_write_approval,
    verify_write_approval,
)


def test_resolve_safe_accepts_valid_path(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "file.txt").write_text("content")
    result = resolve_safe(str(base), "file.txt")
    assert result == base / "file.txt"


def test_resolve_safe_rejects_traversal(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(PathViolationError):
        resolve_safe(str(base), "../etc/passwd")


def test_validate_no_traversal_clean() -> None:
    assert validate_no_traversal("foo/bar.txt") is True


def test_validate_no_traversal_dotdot() -> None:
    assert validate_no_traversal("foo/../bar") is False


def test_validate_no_traversal_absolute() -> None:
    assert validate_no_traversal("/etc/passwd") is False


def test_create_write_approval_has_token() -> None:
    approval = create_write_approval("/path", "abc123")
    assert "token" in approval
    assert approval["normalized_path"] == "/path"
    assert approval["content_hash"] == "abc123"
    assert approval["expires_at"] > time.time()


def test_verify_write_approval_valid() -> None:
    approval = create_write_approval("/path", "hash1", ttl_seconds=3600)
    assert verify_write_approval(approval, "/path", "hash1") is True


def test_verify_write_approval_wrong_path() -> None:
    approval = create_write_approval("/path", "hash1")
    assert verify_write_approval(approval, "/other", "hash1") is False


def test_verify_write_approval_wrong_hash() -> None:
    approval = create_write_approval("/path", "hash1")
    assert verify_write_approval(approval, "/path", "hash2") is False


def test_verify_write_approval_expired() -> None:
    approval = create_write_approval("/path", "hash1", ttl_seconds=-1)
    assert verify_write_approval(approval, "/path", "hash1") is False


# ── security.rbac ─────────────────────────────────────────────────────

from ibreeze.security.rbac import Role, check_permission, require_permission


def test_admin_has_all_permissions() -> None:
    assert check_permission(Role.ADMIN, "company.create")
    assert check_permission(Role.ADMIN, "backup.restore")
    assert check_permission(Role.ADMIN, "settings.update")


def test_user_has_expected_permissions() -> None:
    assert check_permission(Role.USER, "task.create")
    assert check_permission(Role.USER, "knowledge.read")
    assert not check_permission(Role.USER, "admin.*")


def test_guest_limited_permissions() -> None:
    assert check_permission(Role.GUEST, "company.read")
    assert not check_permission(Role.GUEST, "task.create")
    assert not check_permission(Role.GUEST, "company.archive")


def test_wildcard_permission() -> None:
    # Admin has admin.* which matches "admin.anything"
    assert check_permission(Role.ADMIN, "admin.read")
    # admin.* does NOT match "task.read" — need explicit permission
    assert check_permission(Role.ADMIN, "task.read")


def test_require_permission_raises() -> None:
    with pytest.raises(PermissionError):
        require_permission(Role.GUEST, "task.create")


def test_require_permission_succeeds() -> None:
    require_permission(Role.USER, "task.read")


# ── security.redaction ────────────────────────────────────────────────

from ibreeze.security.redaction import redact_string, redact_dict


def test_redact_string_authorization() -> None:
    result = redact_string('Authorization: Bearer abc123')
    assert "[REDACTED]" in result


def test_redact_string_password() -> None:
    result = redact_string('password=secret123')
    assert "[REDACTED]" in result


def test_redact_string_token() -> None:
    result = redact_string('token: xyz789')
    assert "[REDACTED]" in result


def test_redact_string_no_match() -> None:
    text = "this is clean text"
    assert redact_string(text) == text


def test_redact_dict_simple() -> None:
    data = {"user": "admin", "cred": "password=secret123"}
    result = redact_dict(data)
    assert result["user"] == "admin"
    assert "[REDACTED]" in result["cred"]


def test_redact_dict_nested() -> None:
    data = {"config": {"cred": "api_key=key123", "name": "test"}}
    result = redact_dict(data)
    assert result["config"]["name"] == "test"
    assert "[REDACTED]" in result["config"]["cred"]


def test_redact_dict_with_list() -> None:
    data = {"items": ["token: abc", "normal", {"cred": "secret=val"}]}
    result = redact_dict(data)
    assert "[REDACTED]" in result["items"][0]
    assert result["items"][1] == "normal"
    assert "[REDACTED]" in result["items"][2]["cred"]


def test_redact_dict_non_string_values() -> None:
    data = {"count": 42, "active": True, "ratio": 3.14}
    result = redact_dict(data)
    assert result["count"] == 42
    assert result["active"] is True
    assert result["ratio"] == 3.14


# ── security.skill_verify ─────────────────────────────────────────────

from ibreeze.security.skill_verify import (
    SkillVerificationError,
    validate_package_paths,
    compute_package_hash,
)


def test_validate_package_paths_clean(tmp_path: Path) -> None:
    pkg = tmp_path / "skill"
    pkg.mkdir()
    (pkg / "readme.md").write_text("hello")
    sub = pkg / "sub"
    sub.mkdir()
    (sub / "file.py").write_text("code")
    violations = validate_package_paths(str(pkg))
    assert violations == []


def test_validate_package_paths_dotdot(tmp_path: Path) -> None:
    pkg = tmp_path / "skill"
    pkg.mkdir()
    (pkg / "..tricky").mkdir()
    violations = validate_package_paths(str(pkg))
    assert len(violations) == 1


def test_compute_package_hash(tmp_path: Path) -> None:
    f = tmp_path / "test.bin"
    f.write_bytes(b"hello world")
    h = compute_package_hash(str(f))
    assert h == hashlib.sha256(b"hello world").hexdigest()


def test_compute_package_hash_large(tmp_path: Path) -> None:
    f = tmp_path / "large.bin"
    f.write_bytes(os.urandom(100_000))
    h = compute_package_hash(str(f))
    assert len(h) == 64
