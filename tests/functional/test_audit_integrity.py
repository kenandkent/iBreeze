"""Tests for audit log integrity and security.

Covers design spec sections:
- REL-005 Audit log hash chain integrity
- SEC-001 Company isolation in audit logs
"""
import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Hash chain
# ---------------------------------------------------------------------------

class TestAuditIntegrity:
    """Audit log hash chain and integrity checks."""

    @pytest.mark.asyncio
    async def test_audit_log_hash_chain(self):
        """Each audit log entry should chain-hash to previous."""
        from ibreeze.security.audit import _compute_hash, GENESIS_HASH

        row_data_1 = json.dumps(
            {"action": "create", "company_id": "c1"},
            sort_keys=True,
        )
        hash_1 = _compute_hash(row_data_1, GENESIS_HASH)
        assert len(hash_1) == 64

        row_data_2 = json.dumps(
            {"action": "update", "company_id": "c1"},
            sort_keys=True,
        )
        hash_2 = _compute_hash(row_data_2, hash_1)
        assert hash_2 != hash_1
        assert len(hash_2) == 64

        row_data_3 = json.dumps(
            {"action": "delete", "company_id": "c1"},
            sort_keys=True,
        )
        hash_3 = _compute_hash(row_data_3, hash_2)
        assert hash_3 != hash_2
        assert hash_3 != hash_1

    @pytest.mark.asyncio
    async def test_audit_log_tamper_detection(self):
        """Modifying an audit log entry should break the hash chain."""
        from ibreeze.security.audit import _compute_hash, GENESIS_HASH

        row_data = json.dumps(
            {"action": "create", "company_id": "c1"},
            sort_keys=True,
        )
        original_hash = _compute_hash(row_data, GENESIS_HASH)

        tampered_data = json.dumps(
            {"action": "create", "company_id": "c2"},
            sort_keys=True,
        )
        tampered_hash = _compute_hash(tampered_data, GENESIS_HASH)

        assert original_hash != tampered_hash

        next_data = json.dumps({"action": "update"}, sort_keys=True)
        chain_with_original = _compute_hash(next_data, original_hash)
        chain_with_tampered = _compute_hash(next_data, tampered_hash)
        assert chain_with_original != chain_with_tampered

    @pytest.mark.asyncio
    async def test_audit_log_deduplication(self):
        """Duplicate trace_id + action should not create duplicate logs."""
        from ibreeze.security.audit import log_audit

        db = AsyncMock()
        existing = AsyncMock()
        existing.fetchone.return_value = {"id": "existing-id"}
        db.execute.return_value = existing
        db.commit = AsyncMock()

        result = await log_audit(
            db,
            company_id="c1",
            actor_id="a1",
            actor_type="user",
            action="company.create",
            resource_type="company",
            resource_id="r1",
            outcome="success",
            trace_id="trace-dup-1",
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_company_isolation_in_audit(self):
        """SEC-001: Audit logs should be isolated by company_id."""
        from ibreeze.security.audit import list_audit_logs

        db = AsyncMock()
        row_c1 = {
            "row_sequence": 1,
            "id": "id1",
            "company_id": "company-a",
            "actor_type": "user",
            "actor_id": "a1",
            "action": "create",
            "resource_type": "company",
            "resource_id": "r1",
            "outcome": "success",
            "detail_json": "{}",
            "trace_id": "t1",
            "created_at": "2025-01-01T00:00:00Z",
        }
        cursor = AsyncMock()
        cursor.fetchall.return_value = [row_c1]
        db.execute.return_value = cursor

        logs = await list_audit_logs(db, company_id="company-a")
        assert len(logs) == 1
        assert logs[0]["company_id"] == "company-a"

    @pytest.mark.asyncio
    async def test_audit_log_genesis_hash_constant(self):
        """GENESIS_HASH should be 64 zero characters."""
        from ibreeze.security.audit import GENESIS_HASH

        assert GENESIS_HASH == "0" * 64
        assert len(GENESIS_HASH) == 64

    @pytest.mark.asyncio
    async def test_audit_log_new_entry_returns_id(self):
        """Non-duplicate audit log should return a UUID string."""
        from ibreeze.security.audit import log_audit

        db = AsyncMock()
        existing = AsyncMock()
        existing.fetchone.return_value = None
        db.execute.return_value = existing
        db.commit = AsyncMock()

        result = await log_audit(
            db,
            company_id="c1",
            actor_id="a1",
            actor_type="user",
            action="company.create",
            resource_type="company",
            resource_id="r1",
            outcome="success",
            trace_id="trace-unique-1",
        )
        assert isinstance(result, str)
        assert len(result) == 36

    @pytest.mark.asyncio
    async def test_audit_log_without_trace_id_never_deduplicates(self):
        """Empty trace_id should always write a new entry."""
        from ibreeze.security.audit import log_audit

        db = AsyncMock()
        existing = AsyncMock()
        existing.fetchone.return_value = None
        db.execute.return_value = existing
        db.commit = AsyncMock()

        result = await log_audit(
            db,
            company_id="c1",
            actor_id="a1",
            actor_type="user",
            action="company.create",
            resource_type="company",
            resource_id="r1",
            outcome="success",
            trace_id="",
        )
        assert isinstance(result, str)
        assert len(result) == 36
