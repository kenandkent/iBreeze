"""Coverage tests for security.encryption.migrate_password and audit branches.

Targets the uncovered lines/arcs:
- encryption.py: migrate_password full path (83-92)
- audit.py: dedup-no-match arc 103->106, list_audit_logs filters 169-170,
  172-173, 175-176
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ibreeze.security.audit import list_audit_logs, log_audit
from ibreeze.security.encryption import migrate_password

# ── encryption.migrate_password (83-92) ────────────────────────────────────


class TestMigratePasswordCoverage:
    def test_non_bcrypt_hash_returns_none(self):
        """encryption.py:83-84 — non-bcrypt old hash is rejected."""
        assert migrate_password("pw", "$argon2id$v=19$m=65536") is None

    def test_valid_bcrypt_hash_migrates_to_argon2id(self):
        """encryption.py:85,87-88 — matching bcrypt hash returns Argon2id hash."""
        import bcrypt

        old_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        result = migrate_password("secret", old_hash)
        assert result is not None
        assert result.startswith("$argon2id$")

    def test_wrong_password_returns_none(self):
        """encryption.py:92 — bcrypt mismatch returns None."""
        import bcrypt

        old_hash = bcrypt.hashpw(b"secret", bcrypt.gensalt()).decode()
        assert migrate_password("wrong", old_hash) is None

    def test_malformed_bcrypt_hash_returns_none(self):
        """encryption.py:90-92 — checkpw exception is swallowed and returns None."""
        assert migrate_password("pw", "$2b$12$not-a-real-hash") is None


# ── audit.log_audit dedup no-match (103->106) ──────────────────────────────


@pytest.mark.asyncio
class TestLogAuditDedupNoMatch:
    async def test_dedup_miss_continues_to_insert(self):
        """audit.py:103->106 — dedup query with no row still logs the entry."""
        mock_db = AsyncMock()
        dedup_cursor = AsyncMock()
        dedup_cursor.fetchone.return_value = None
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
            trace_id="trace-abc",
        )
        assert result  # a new log id was inserted
        assert mock_db.execute.await_count == 3


# ── audit.list_audit_logs filters (169-176) ────────────────────────────────


@pytest.mark.asyncio
class TestListAuditLogsFilters:
    async def test_all_filters_appended(self):
        """audit.py:169-170,172-173,175-176 — optional filters build the WHERE."""
        mock_db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = [{"id": "1", "action": "login"}]
        mock_db.execute.return_value = cursor
        result = await list_audit_logs(
            mock_db,
            company_id="c1",
            actor_id="a1",
            action="login",
            resource_type="user",
            after_sequence=5,
            limit=10,
        )
        assert len(result) == 1
        sql = mock_db.execute.await_args.args[0]
        assert "company_id = ?" in sql
        assert "actor_id = ?" in sql
        assert "action = ?" in sql
        assert "resource_type = ?" in sql
        params = mock_db.execute.await_args.args[1]
        assert params == (5, "c1", "a1", "login", "user", 10)
