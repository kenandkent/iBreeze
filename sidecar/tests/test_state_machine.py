"""状态机单元测试。

覆盖 H.7 全部 9 种聚合的 ALLOWED_TRANSITIONS 表，
验证合法迁移、非法迁移、终态和 resume_state 逻辑。
"""

import pytest

from ibreeze.state_machine import (
    StateTransitionError,
    can_transition,
    get_allowed_targets,
    is_terminal,
    transition,
    validate_resume_state,
)

# ── CompanyTask ────────────────────────────────────────────────────────────


class TestCompanyTaskStateMachine:
    def test_draft_to_analyzing(self):
        assert can_transition("CompanyTask", "draft", "analyzing")

    def test_draft_to_cancelling(self):
        assert can_transition("CompanyTask", "draft", "cancelling")

    def test_draft_rejects_running(self):
        assert not can_transition("CompanyTask", "draft", "executing")

    def test_analyzing_to_awaiting(self):
        assert can_transition("CompanyTask", "analyzing", "awaiting_user_confirmation")

    def test_analyzing_to_failed(self):
        assert can_transition("CompanyTask", "analyzing", "failed")

    def test_awaiting_to_approved(self):
        assert can_transition("CompanyTask", "awaiting_user_confirmation", "approved")

    def test_awaiting_to_revision_requested(self):
        assert can_transition("CompanyTask", "awaiting_user_confirmation", "revision_requested")

    def test_awaiting_to_rejected(self):
        assert can_transition("CompanyTask", "awaiting_user_confirmation", "rejected")

    def test_approved_to_dispatching(self):
        assert can_transition("CompanyTask", "approved", "dispatching")

    def test_dispatching_to_checking(self):
        assert can_transition("CompanyTask", "dispatching", "checking_resources")

    def test_executing_to_reviewing(self):
        assert can_transition("CompanyTask", "executing", "reviewing")

    def test_reviewing_to_fixing(self):
        assert can_transition("CompanyTask", "reviewing", "fixing")

    def test_reviewing_to_final_review(self):
        assert can_transition("CompanyTask", "reviewing", "final_review")

    def test_final_review_to_completed(self):
        assert can_transition("CompanyTask", "final_review", "completed")

    def test_completed_is_terminal(self):
        assert is_terminal("CompanyTask", "completed")

    def test_cancelled_is_terminal(self):
        assert is_terminal("CompanyTask", "cancelled")

    def test_failed_is_terminal(self):
        assert is_terminal("CompanyTask", "failed")

    def test_rejected_is_terminal(self):
        assert is_terminal("CompanyTask", "rejected")

    def test_waiting_to_cancelled(self):
        assert can_transition("CompanyTask", "waiting_resource", "cancelling")

    def test_paused_to_cancelled(self):
        assert can_transition("CompanyTask", "paused", "cancelling")

    def test_get_allowed_targets_draft(self):
        targets = get_allowed_targets("CompanyTask", "draft")
        assert targets == {"analyzing", "cancelling"}

    def test_get_allowed_targets_completed(self):
        assert get_allowed_targets("CompanyTask", "completed") == frozenset()


# ── DepartmentTask ─────────────────────────────────────────────────────────


class TestDepartmentTaskStateMachine:
    def test_draft_to_checking(self):
        assert can_transition("DepartmentTask", "draft", "checking_resources")

    def test_draft_to_cancelled(self):
        assert can_transition("DepartmentTask", "draft", "cancelled")

    def test_ready_to_executing(self):
        assert can_transition("DepartmentTask", "ready", "executing")

    def test_executing_to_reviewing(self):
        assert can_transition("DepartmentTask", "executing", "reviewing")

    def test_reviewing_to_completed(self):
        assert can_transition("DepartmentTask", "reviewing", "completed")

    def test_reviewing_to_fixing(self):
        assert can_transition("DepartmentTask", "reviewing", "fixing")

    def test_fixing_to_reviewing(self):
        assert can_transition("DepartmentTask", "fixing", "reviewing")

    def test_completed_is_terminal(self):
        assert is_terminal("DepartmentTask", "completed")

    def test_cancelled_is_terminal(self):
        assert is_terminal("DepartmentTask", "cancelled")

    def test_draft_rejects_executing(self):
        assert not can_transition("DepartmentTask", "draft", "executing")


# ── EmployeeTask ───────────────────────────────────────────────────────────


class TestEmployeeTaskStateMachine:
    def test_assigned_to_ready(self):
        assert can_transition("EmployeeTask", "assigned", "ready")

    def test_ready_to_running(self):
        assert can_transition("EmployeeTask", "ready", "running")

    def test_running_to_submitted(self):
        assert can_transition("EmployeeTask", "running", "submitted")

    def test_submitted_to_peer_reviewing(self):
        assert can_transition("EmployeeTask", "submitted", "peer_reviewing")

    def test_peer_reviewing_to_accepted(self):
        assert can_transition("EmployeeTask", "peer_reviewing", "accepted")

    def test_peer_reviewing_to_changes_requested(self):
        assert can_transition("EmployeeTask", "peer_reviewing", "changes_requested")

    def test_changes_requested_to_ready(self):
        assert can_transition("EmployeeTask", "changes_requested", "ready")

    def test_accepted_is_terminal(self):
        assert is_terminal("EmployeeTask", "accepted")

    def test_cancelled_is_terminal(self):
        assert is_terminal("EmployeeTask", "cancelled")

    def test_running_to_waiting_resource(self):
        assert can_transition("EmployeeTask", "running", "waiting_resource")


# ── AgentRun ───────────────────────────────────────────────────────────────


class TestAgentRunStateMachine:
    def test_queued_to_probing(self):
        assert can_transition("AgentRun", "queued", "probing")

    def test_queued_to_cancelled(self):
        assert can_transition("AgentRun", "queued", "cancelled")

    def test_probing_to_starting(self):
        assert can_transition("AgentRun", "probing", "starting")

    def test_starting_to_running(self):
        assert can_transition("AgentRun", "starting", "running")

    def test_starting_to_retrying(self):
        assert can_transition("AgentRun", "starting", "retrying")

    def test_running_to_verifying(self):
        assert can_transition("AgentRun", "running", "verifying")

    def test_running_to_waiting_approval(self):
        assert can_transition("AgentRun", "running", "waiting_approval")

    def test_running_to_lost(self):
        assert can_transition("AgentRun", "running", "lost")

    def test_verifying_to_succeeded(self):
        assert can_transition("AgentRun", "verifying", "succeeded")

    def test_retrying_to_starting(self):
        assert can_transition("AgentRun", "retrying", "starting")

    def test_lost_to_retrying(self):
        assert can_transition("AgentRun", "lost", "retrying")

    def test_succeeded_is_terminal(self):
        assert is_terminal("AgentRun", "succeeded")

    def test_timed_out_is_terminal(self):
        assert is_terminal("AgentRun", "timed_out")

    def test_lost_rejects_succeeded(self):
        assert not can_transition("AgentRun", "lost", "succeeded")


# ── ReviewAssignment ──────────────────────────────────────────────────────


class TestReviewAssignmentStateMachine:
    def test_assigned_to_in_review(self):
        assert can_transition("ReviewAssignment", "assigned", "in_review")

    def test_in_review_to_submitted(self):
        assert can_transition("ReviewAssignment", "in_review", "submitted")

    def test_submitted_to_stale(self):
        assert can_transition("ReviewAssignment", "submitted", "stale")

    def test_stale_is_terminal(self):
        assert is_terminal("ReviewAssignment", "stale")

    def test_cancelled_is_terminal(self):
        assert is_terminal("ReviewAssignment", "cancelled")


# ── ReviewIssue ────────────────────────────────────────────────────────────


class TestReviewIssueStateMachine:
    def test_open_to_fixing(self):
        assert can_transition("ReviewIssue", "open", "fixing")

    def test_open_to_rejected(self):
        assert can_transition("ReviewIssue", "open", "rejected")

    def test_fixing_to_resolved(self):
        assert can_transition("ReviewIssue", "fixing", "resolved")

    def test_resolved_to_verified(self):
        assert can_transition("ReviewIssue", "resolved", "verified")

    def test_resolved_to_fixing(self):
        assert can_transition("ReviewIssue", "resolved", "fixing")

    def test_verified_to_closed(self):
        assert can_transition("ReviewIssue", "verified", "closed")

    def test_verified_to_fixing(self):
        assert can_transition("ReviewIssue", "verified", "fixing")

    def test_closed_is_terminal(self):
        assert is_terminal("ReviewIssue", "closed")

    def test_rejected_is_terminal(self):
        assert is_terminal("ReviewIssue", "rejected")


# ── CompanyPlanVersion ────────────────────────────────────────────────────


class TestCompanyPlanVersionStateMachine:
    def test_draft_to_awaiting(self):
        assert can_transition("CompanyPlanVersion", "draft", "awaiting_user_confirmation")

    def test_draft_to_rejected(self):
        assert can_transition("CompanyPlanVersion", "draft", "rejected")

    def test_awaiting_to_approved(self):
        assert can_transition("CompanyPlanVersion", "awaiting_user_confirmation", "approved")

    def test_awaiting_to_superseded(self):
        assert can_transition("CompanyPlanVersion", "awaiting_user_confirmation", "superseded")

    def test_approved_is_terminal(self):
        assert is_terminal("CompanyPlanVersion", "approved")

    def test_superseded_is_terminal(self):
        assert is_terminal("CompanyPlanVersion", "superseded")


# ── TaskWorkspace ──────────────────────────────────────────────────────────


class TestTaskWorkspaceStateMachine:
    def test_preparing_to_active(self):
        assert can_transition("TaskWorkspace", "preparing", "active")

    def test_active_to_ready_to_apply(self):
        assert can_transition("TaskWorkspace", "active", "ready_to_apply")

    def test_ready_to_apply_to_applied(self):
        assert can_transition("TaskWorkspace", "ready_to_apply", "applied")

    def test_applied_is_terminal(self):
        assert is_terminal("TaskWorkspace", "applied")

    def test_abandoned_is_terminal(self):
        assert is_terminal("TaskWorkspace", "abandoned")


# ── HumanApproval ─────────────────────────────────────────────────────────


class TestHumanApprovalStateMachine:
    def test_pending_to_allowed(self):
        assert can_transition("HumanApproval", "pending", "allowed")

    def test_pending_to_denied(self):
        assert can_transition("HumanApproval", "pending", "denied")

    def test_pending_to_expired(self):
        assert can_transition("HumanApproval", "pending", "expired")

    def test_allowed_to_consumed(self):
        assert can_transition("HumanApproval", "allowed", "consumed")

    def test_allowed_to_expired(self):
        assert can_transition("HumanApproval", "allowed", "expired")

    def test_denied_is_terminal(self):
        assert is_terminal("HumanApproval", "denied")

    def test_consumed_is_terminal(self):
        assert is_terminal("HumanApproval", "consumed")


# ── 泛型函数 ──────────────────────────────────────────────────────────────


class TestTransitionFunction:
    def test_valid_transition_returns_none(self):
        result = transition("CompanyTask", "draft", "analyzing")
        assert result is None

    def test_invalid_transition_raises(self):
        with pytest.raises(StateTransitionError) as exc_info:
            transition("CompanyTask", "draft", "completed")
        assert exc_info.value.entity == "CompanyTask"
        assert exc_info.value.current == "draft"
        assert exc_info.value.target == "completed"

    def test_terminal_state_raises(self):
        with pytest.raises(StateTransitionError):
            transition("CompanyTask", "completed", "executing")

    def test_unknown_entity_raises(self):
        with pytest.raises(ValueError, match="Unknown entity"):
            transition("NonExistent", "a", "b")

    def test_unknown_state_raises(self):
        with pytest.raises(ValueError, match="Unknown state"):
            transition("CompanyTask", "nonexistent", "analyzing")


class TestValidateResumeState:
    def test_waiting_state_requires_resume(self):
        with pytest.raises(ValueError, match="resume_state required"):
            validate_resume_state("CompanyTask", "waiting_resource", None)

    def test_non_waiting_state_rejects_resume(self):
        with pytest.raises(ValueError, match="resume_state must be null"):
            validate_resume_state("CompanyTask", "executing", "running")

    def test_waiting_state_with_resume_ok(self):
        validate_resume_state("CompanyTask", "waiting_resource", "executing")

    def test_non_waiting_state_without_resume_ok(self):
        validate_resume_state("CompanyTask", "executing", None)
