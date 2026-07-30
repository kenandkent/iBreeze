"""Tests for approval advanced scenarios.

Covers design spec sections:
- APR-002 Approval should detect target changes
- APR-003 Lost execution receipt recovery
- APR-004 Uncertain outcomes require manual approval
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
class TestApprovalAdvanced:
    """Approval advanced scenario tests."""

    async def test_approval_after_target_change(self):
        """APR-002: Approval should detect target changes."""
        from ibreeze.approvals.service import request_external_write_approval

        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        result = await request_external_write_approval(
            db,
            "c1",
            run_id="run-1",
            employee_id="emp-1",
            target_path="/workspace/file.py",
            action="write",
            old_hash="abc123",
            new_hash="def456",
        )
        assert result["status"] == "pending"
        assert result["target_path"] == "/workspace/file.py"
        assert result["action"] == "write"
        assert result["approval_type"] == "external_write"

    async def test_receipt_lost_recovery(self):
        """APR-003: Should handle lost execution receipts."""
        from ibreeze.approvals.service import list_pending_approvals

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {
                "id": "approval-1",
                "company_id": "c1",
                "approval_type": "external_write",
                "status": "pending",
                "target_path": "/workspace/file.py",
            }
        ]
        db.execute.return_value = cursor

        approvals = await list_pending_approvals(db, "c1")
        assert len(approvals) == 1
        assert approvals[0]["status"] == "pending"

    async def test_uncertain_recovery_approval(self):
        """APR-004: Uncertain outcomes should require manual approval."""
        from ibreeze.approvals.service import request_uncertain_recovery_approval

        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()

        result = await request_uncertain_recovery_approval(
            db,
            "c1",
            run_id="run-2",
            employee_id="emp-2",
            reason="Agent crashed during write, state unknown",
        )
        assert result["status"] == "pending"
        assert result["approval_type"] == "uncertain_recovery"
        assert "unknown" in result["reason"].lower()

    async def test_resolve_approval_approve(self):
        """Approving a pending request should set status to approved."""
        from ibreeze.approvals.service import resolve_approval

        db = AsyncMock()
        approval_row = {
            "id": "appr-1",
            "company_id": "c1",
            "status": "pending",
        }
        cursor = AsyncMock()
        cursor.fetchone.return_value = approval_row
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        result = await resolve_approval(
            db,
            "c1",
            approval_id="appr-1",
            decision="approve",
            resolved_by_employee_id="emp-admin",
            receipt_hash="receipt-hash-1",
        )
        assert result["status"] == "approved"
        assert result["resolved_by"] == "emp-admin"

    async def test_resolve_approval_deny(self):
        """Denying a pending request should set status to denied."""
        from ibreeze.approvals.service import resolve_approval

        db = AsyncMock()
        approval_row = {
            "id": "appr-2",
            "company_id": "c1",
            "status": "pending",
        }
        cursor = AsyncMock()
        cursor.fetchone.return_value = approval_row
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        result = await resolve_approval(
            db,
            "c1",
            approval_id="appr-2",
            decision="deny",
            resolved_by_employee_id="emp-admin",
        )
        assert result["status"] == "denied"

    async def test_resolve_nonexistent_approval(self):
        """Resolving a non-existent approval should raise error."""
        from ibreeze.approvals.service import resolve_approval

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone.return_value = None
        db.execute.return_value = cursor

        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await resolve_approval(
                db,
                "c1",
                approval_id="nonexistent",
                decision="approve",
                resolved_by_employee_id="emp-admin",
            )

    async def test_resolve_already_resolved_approval(self):
        """Resolving an already-resolved approval should raise error."""
        from ibreeze.approvals.service import resolve_approval

        db = AsyncMock()
        approval_row = {
            "id": "appr-3",
            "company_id": "c1",
            "status": "approved",
        }
        cursor = AsyncMock()
        cursor.fetchone.return_value = approval_row
        db.execute.return_value = cursor

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await resolve_approval(
                db,
                "c1",
                approval_id="appr-3",
                decision="approve",
                resolved_by_employee_id="emp-admin",
            )

    async def test_expire_stale_approvals(self):
        """Expired approvals should be marked as expired."""
        from ibreeze.approvals.service import expire_stale_approvals

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.rowcount = 2
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        expired_count = await expire_stale_approvals(db, "c1")
        assert expired_count == 2

    async def test_list_pending_approvals_with_type_filter(self):
        """Filtering by approval_type should narrow results."""
        from ibreeze.approvals.service import list_pending_approvals

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = [
            {
                "id": "appr-4",
                "approval_type": "uncertain_recovery",
                "status": "pending",
            }
        ]
        db.execute.return_value = cursor

        approvals = await list_pending_approvals(
            db, "c1", approval_type="uncertain_recovery"
        )
        assert len(approvals) == 1
        assert approvals[0]["approval_type"] == "uncertain_recovery"
