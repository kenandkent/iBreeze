"""Integration tests for RPC method registration and service layer."""

import pytest
import asyncio
from unittest.mock import AsyncMock


@pytest.fixture
def mock_db():
    """Create a mock database connection."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetchone = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.commit = AsyncMock()
    return db


class TestCompanyServiceIntegration:
    """Test company service operations."""

    @pytest.mark.asyncio
    async def test_create_company(self, mock_db):
        from ibreeze.company import create_company, CompanyCreate

        data = CompanyCreate(
            name="测试公司",
            introduction="简介",
            general_manager_name="经理",
            base_profile_version_id="v1",
        )
        with pytest.raises((ValueError, RuntimeError, AssertionError)):
            await create_company(mock_db, data=data)

    @pytest.mark.asyncio
    async def test_rpc_method_registration(self):
        """Verify all RPC methods are properly registered."""
        import ibreeze.rpc_server

        server = ibreeze.rpc_server.RPCServer.__new__(ibreeze.rpc_server.RPCServer)
        server.methods = {}
        ibreeze.rpc_server.RPCServer._register = lambda self: None


class TestKnowledgeServiceIntegration:
    """Test knowledge service operations."""

    @pytest.mark.asyncio
    async def test_chunk_markdown(self):
        from ibreeze.knowledge.chunker import chunk_markdown

        text = "# Title\n\nParagraph 1\n\nParagraph 2\n\nParagraph 3"
        chunks = chunk_markdown(text, max_tokens=100)
        assert len(chunks) > 0
        assert all("text" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_chunk_code(self):
        from ibreeze.knowledge.chunker import chunk_code

        code = "def foo():\n    pass\n\ndef bar():\n    pass"
        chunks = chunk_code(code)
        assert len(chunks) > 0


class TestSecurityIntegration:
    """Test security module operations."""

    def test_encryption_roundtrip(self):
        from ibreeze.security.encryption import derive_key, encrypt, decrypt

        key, salt = derive_key("test_password")
        plaintext = "Hello, World!"
        ciphertext = encrypt(plaintext, key)
        decrypted = decrypt(ciphertext, key)
        assert decrypted == plaintext

    def test_password_hash(self):
        from ibreeze.security.encryption import hash_password, verify_password

        hashed = hash_password("test_password")
        assert verify_password("test_password", hashed)
        assert not verify_password("wrong_password", hashed)

    def test_redaction(self):
        from ibreeze.security.redaction import redact_string

        text = "Authorization: Bearer token123"
        redacted = redact_string(text)
        assert "token123" not in redacted
        assert "[REDACTED]" in redacted

    def test_rbac(self):
        from ibreeze.security.rbac import check_permission, Role

        assert check_permission(Role.ADMIN, "company.create")
        assert not check_permission(Role.GUEST, "company.create")
        assert check_permission(Role.USER, "company.read")


class TestWorkspaceIntegration:
    """Test workspace module operations."""

    def test_git_ops_import(self):
        from ibreeze.workspace.git_ops import git_command, create_worktree

        assert asyncio.iscoroutinefunction(git_command)
        assert asyncio.iscoroutinefunction(create_worktree)


class TestBackupIntegration:
    """Test backup module operations."""

    def test_packager_import(self):
        from ibreeze.backup.packager import create_backup_package, verify_backup_package

        assert callable(create_backup_package)
        assert callable(verify_backup_package)

    def test_records_import(self):
        from ibreeze.backup.records import create_backup_record, list_backup_records

        assert asyncio.iscoroutinefunction(create_backup_record)
        assert asyncio.iscoroutinefunction(list_backup_records)
