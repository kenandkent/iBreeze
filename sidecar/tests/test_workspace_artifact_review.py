"""Tests for Workspace/Artifact/Review/Approval services."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ibreeze.artifacts.service import (
    create_artifact,
    get_artifact,
    list_artifacts,
    get_artifact_version_chain,
)
from ibreeze.review.service import (
    assign_reviewer,
    submit_review_report,
    create_review_issue,
    resolve_review_issue,
    list_review_issues,
)
from ibreeze.approvals.service import (
    request_external_write_approval,
    request_uncertain_recovery_approval,
    resolve_approval,
    list_pending_approvals,
    expire_stale_approvals,
)


class TestArtifactService:
    """Tests for artifact CAS service."""

    @pytest.mark.asyncio
    async def test_create_artifact(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(fetchone=AsyncMock(return_value=None)))
        result = await create_artifact(
            mock_db_session,
            "comp-1",
            company_task_id="task-1",
            artifact_type="source_code_patch",
            content=b"test content",
            filename="test.py",
            mime_type="text/plain",
            created_by_employee_id="emp-1",
        )
        assert "id" in result
        assert result["deduplicated"] is False

    @pytest.mark.asyncio
    async def test_create_artifact_deduplication(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"id": "existing-id"})
        ))
        result = await create_artifact(
            mock_db_session,
            "comp-1",
            company_task_id="task-1",
            artifact_type="source_code_patch",
            content=b"test content",
            filename="test.py",
            mime_type="text/plain",
            created_by_employee_id="emp-1",
        )
        assert result["deduplicated"] is True
        assert result["id"] == "existing-id"

    @pytest.mark.asyncio
    async def test_get_artifact(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"id": "art-1", "filename": "test.py"})
        ))
        result = await get_artifact(mock_db_session, "comp-1", "art-1")
        assert result["id"] == "art-1"

    @pytest.mark.asyncio
    async def test_list_artifacts(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=AsyncMock(return_value=[{"id": "art-1"}, {"id": "art-2"}])
        ))
        result = await list_artifacts(mock_db_session, "comp-1")
        assert len(result) == 2


class TestReviewService:
    """Tests for review service."""

    @pytest.mark.asyncio
    async def test_assign_reviewer(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value=None)
        ))
        result = await assign_reviewer(
            mock_db_session,
            "comp-1",
            artifact_id="art-1",
            reviewer_employee_id="emp-2",
            review_round=1,
            reviewed_sha256="abc123",
        )
        assert result["status"] == "assigned"

    @pytest.mark.asyncio
    async def test_assign_reviewer_rejects_contributor(self, mock_db_session):
        # First call: check contributor - returns contributor
        result1 = MagicMock()
        result1.fetchone = AsyncMock(return_value={"id": "contributor"})

        mock_db_session.execute = AsyncMock(return_value=result1)
        mock_db_session.commit = AsyncMock()
        mock_db_session.rollback = AsyncMock()

        with pytest.raises(ValueError, match="REVIEWER_CANNOT_BE_CONTRIBUTOR"):
            await assign_reviewer(
                mock_db_session,
                "comp-1",
                artifact_id="art-1",
                reviewer_employee_id="emp-1",
                review_round=1,
                reviewed_sha256="abc123",
            )

    @pytest.mark.asyncio
    async def test_create_review_issue(self, mock_db_session):
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()
        result = await create_review_issue(
            mock_db_session,
            "comp-1",
            report_id="rep-1",
            severity="high",
            description="Bug found",
        )
        assert result["status"] == "open"


class TestApprovalService:
    """Tests for approval service."""

    @pytest.mark.asyncio
    async def test_request_external_write_approval(self, mock_db_session):
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()
        result = await request_external_write_approval(
            mock_db_session,
            "comp-1",
            run_id="run-1",
            employee_id="emp-1",
            target_path="/tmp/test.txt",
            action="write",
            old_hash=None,
            new_hash="abc123",
        )
        assert result["status"] == "pending"
        assert result["approval_type"] == "external_write"

    @pytest.mark.asyncio
    async def test_request_uncertain_recovery_approval(self, mock_db_session):
        mock_db_session.execute = AsyncMock()
        mock_db_session.commit = AsyncMock()
        result = await request_uncertain_recovery_approval(
            mock_db_session,
            "comp-1",
            run_id="run-1",
            employee_id="emp-1",
            reason="Database corrupted",
        )
        assert result["status"] == "pending"
        assert result["approval_type"] == "uncertain_recovery"

    @pytest.mark.asyncio
    async def test_resolve_approval_approve(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"id": "app-1", "status": "pending"})
        ))
        mock_db_session.commit = AsyncMock()
        result = await resolve_approval(
            mock_db_session,
            "comp-1",
            approval_id="app-1",
            decision="approve",
            resolved_by_employee_id="emp-2",
        )
        assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_resolve_approval_not_found(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value=None)
        ))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await resolve_approval(
                mock_db_session,
                "comp-1",
                approval_id="nonexistent",
                decision="approve",
                resolved_by_employee_id="emp-2",
            )

    @pytest.mark.asyncio
    async def test_list_pending_approvals(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=AsyncMock(return_value=[{"id": "app-1", "status": "pending"}])
        ))
        result = await list_pending_approvals(mock_db_session, "comp-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_pending_approvals_with_type(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=AsyncMock(return_value=[{"id": "app-1", "status": "pending", "approval_type": "external_write"}])
        ))
        result = await list_pending_approvals(mock_db_session, "comp-1", approval_type="external_write")
        assert len(result) == 1
        assert result[0]["approval_type"] == "external_write"

    @pytest.mark.asyncio
    async def test_expire_stale_approvals(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(rowcount=2))
        mock_db_session.commit = AsyncMock()
        result = await expire_stale_approvals(mock_db_session, "comp-1")
        assert result == 2

    @pytest.mark.asyncio
    async def test_resolve_approval_deny(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"id": "app-1", "status": "pending"})
        ))
        mock_db_session.commit = AsyncMock()
        result = await resolve_approval(
            mock_db_session,
            "comp-1",
            approval_id="app-1",
            decision="deny",
            resolved_by_employee_id="emp-2",
        )
        assert result["status"] == "denied"

    @pytest.mark.asyncio
    async def test_resolve_approval_already_resolved(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"id": "app-1", "status": "approved"})
        ))
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await resolve_approval(
                mock_db_session,
                "comp-1",
                approval_id="app-1",
                decision="approve",
                resolved_by_employee_id="emp-2",
            )


class TestArtifactExtended:
    """Extended tests for artifact service."""

    @pytest.mark.asyncio
    async def test_get_artifact_version_chain(self, mock_db_session):
        # Mock chain: art-1 -> art-2 -> None
        call_count = 0
        async def mock_execute(sql, params=()):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(fetchone=AsyncMock(return_value={"id": "art-1", "supersedes_artifact_id": "art-2"}))
            elif call_count == 2:
                return MagicMock(fetchone=AsyncMock(return_value={"id": "art-2", "supersedes_artifact_id": None}))
            return MagicMock(fetchone=AsyncMock(return_value=None))
        
        mock_db_session.execute = mock_execute
        result = await get_artifact_version_chain(mock_db_session, "comp-1", "art-1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_artifacts_with_filters(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=AsyncMock(return_value=[{"id": "art-1", "artifact_type": "code"}])
        ))
        result = await list_artifacts(
            mock_db_session,
            "comp-1",
            company_task_id="task-1",
            artifact_type="code",
            limit=10
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create_artifact_error_rollback(self, mock_db_session):
        call_count = 0
        async def mock_execute(sql, params=()):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # BEGIN IMMEDIATE
                return MagicMock()
            # Simulate error on INSERT
            raise Exception("DB error")
        
        mock_db_session.execute = mock_execute
        mock_db_session.rollback = AsyncMock()
        mock_db_session.commit = AsyncMock()
        
        with pytest.raises(Exception, match="DB error"):
            await create_artifact(
                mock_db_session,
                "comp-1",
                company_task_id="task-1",
                artifact_type="code",
                content=b"test",
                filename="test.py",
                mime_type="text/plain",
                created_by_employee_id="emp-1",
            )


class TestReviewExtended:
    """Extended tests for review service."""

    @pytest.mark.asyncio
    async def test_submit_review_report(self, mock_db_session):
        # Mock execute to return different values based on call order
        call_count = 0
        async def mock_execute(sql, params=()):
            nonlocal call_count
            call_count += 1
            if "BEGIN" in sql:
                return MagicMock()
            if "review_assignments" in sql and "SELECT" in sql:
                return MagicMock(fetchone=AsyncMock(return_value={"id": "asgn-1", "status": "assigned"}))
            return MagicMock()
        
        mock_db_session.execute = mock_execute
        mock_db_session.commit = AsyncMock()
        mock_db_session.rollback = AsyncMock()
        
        result = await submit_review_report(
            mock_db_session,
            "comp-1",
            assignment_id="asgn-1",
            report_artifact_id="rep-art-1",
            verdict="approved",
            summary="Looks good",
        )
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_submit_review_report_not_found(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value=None)
        ))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await submit_review_report(
                mock_db_session,
                "comp-1",
                assignment_id="nonexistent",
                report_artifact_id="rep-art-1",
                verdict="approved",
                summary="Looks good",
            )

    @pytest.mark.asyncio
    async def test_submit_review_report_invalid_state(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchone=AsyncMock(return_value={"id": "asgn-1", "status": "completed"})
        ))
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await submit_review_report(
                mock_db_session,
                "comp-1",
                assignment_id="asgn-1",
                report_artifact_id="rep-art-1",
                verdict="approved",
                summary="Looks good",
            )

    @pytest.mark.asyncio
    async def test_resolve_review_issue(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        mock_db_session.commit = AsyncMock()
        
        result = await resolve_review_issue(
            mock_db_session,
            "comp-1",
            issue_id="issue-1",
            resolution="Fixed in commit abc",
        )
        assert result["status"] == "resolved"

    @pytest.mark.asyncio
    async def test_resolve_review_issue_not_found(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await resolve_review_issue(
                mock_db_session,
                "comp-1",
                issue_id="nonexistent",
                resolution="Fixed",
            )

    @pytest.mark.asyncio
    async def test_list_review_issues(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=AsyncMock(return_value=[{"id": "issue-1", "severity": "high"}])
        ))
        result = await list_review_issues(mock_db_session, "comp-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_review_issues_with_filters(self, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            fetchall=AsyncMock(return_value=[{"id": "issue-1", "status": "open"}])
        ))
        result = await list_review_issues(
            mock_db_session,
            "comp-1",
            report_id="rep-1",
            status="open",
            limit=5
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_assign_reviewer_already_assigned(self, mock_db_session):
        # Mock execute to return different values based on call order
        # Call 1: BEGIN IMMEDIATE
        # Call 2: contributor check - returns None (not a contributor)
        # Call 3: already assigned check - returns existing assignment
        call_count = 0
        async def mock_execute(sql, params=()):
            nonlocal call_count
            call_count += 1
            if "BEGIN" in sql:
                return MagicMock()
            if "artifact_contributors" in sql:
                return MagicMock(fetchone=AsyncMock(return_value=None))
            if "review_assignments" in sql:
                return MagicMock(fetchone=AsyncMock(return_value={"id": "existing"}))
            return MagicMock()
        
        mock_db_session.execute = mock_execute
        mock_db_session.commit = AsyncMock()
        mock_db_session.rollback = AsyncMock()
        
        with pytest.raises(ValueError, match="REVIEWER_ALREADY_ASSIGNED"):
            await assign_reviewer(
                mock_db_session,
                "comp-1",
                artifact_id="art-1",
                reviewer_employee_id="emp-2",
                review_round=1,
                reviewed_sha256="abc123",
            )
