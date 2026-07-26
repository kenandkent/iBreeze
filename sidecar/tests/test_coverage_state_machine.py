"""Tests to improve state machine coverage: edge cases, error paths."""

from __future__ import annotations

import pytest

from ibreeze.state_machine import (
    CompanyTaskState,
    EmployeeTaskState,
    StateTransitionError,
    can_transition,
    get_allowed_targets,
    is_terminal,
    transition,
    validate_resume_state,
)


# ── is_terminal ────────────────────────────────────────────────────────


class TestIsTerminal:
    def test_company_task_completed_is_terminal(self):
        assert is_terminal("CompanyTask", "completed") is True

    def test_company_task_cancelled_is_terminal(self):
        assert is_terminal("CompanyTask", "cancelled") is True

    def test_company_task_failed_is_terminal(self):
        assert is_terminal("CompanyTask", "failed") is True

    def test_company_task_draft_not_terminal(self):
        assert is_terminal("CompanyTask", "draft") is False

    def test_company_task_executing_not_terminal(self):
        assert is_terminal("CompanyTask", "executing") is False

    def test_unknown_entity_raises(self):
        with pytest.raises(ValueError, match="Unknown entity type"):
            is_terminal("nonexistent", "state")

    def test_unknown_state_raises(self):
        with pytest.raises(ValueError, match="Unknown state"):
            is_terminal("CompanyTask", "nonexistent_state")

    def test_employee_task_accepted_is_terminal(self):
        assert is_terminal("EmployeeTask", "accepted") is True

    def test_employee_task_cancelled_is_terminal(self):
        assert is_terminal("EmployeeTask", "cancelled") is True

    def test_employee_task_assigned_not_terminal(self):
        assert is_terminal("EmployeeTask", "assigned") is False

    def test_employee_task_running_not_terminal(self):
        assert is_terminal("EmployeeTask", "running") is False


# ── can_transition ─────────────────────────────────────────────────────


class TestCanTransition:
    def test_valid_transition(self):
        assert can_transition("CompanyTask", "draft", "analyzing") is True

    def test_invalid_transition(self):
        assert can_transition("CompanyTask", "completed", "draft") is False

    def test_unknown_entity_raises(self):
        with pytest.raises(ValueError, match="Unknown entity type"):
            can_transition("nonexistent", "a", "b")

    def test_unknown_current_state_raises(self):
        with pytest.raises(ValueError, match="Unknown state"):
            can_transition("CompanyTask", "nonexistent", "draft")

    def test_waiting_to_failed(self):
        assert can_transition("CompanyTask", "waiting_dependency", "failed") is True

    def test_waiting_to_cancelling(self):
        assert can_transition("CompanyTask", "waiting_permission", "cancelling") is True

    def test_paused_to_failed(self):
        assert can_transition("CompanyTask", "paused", "failed") is True

    def test_employee_task_assigned_to_ready(self):
        assert can_transition("EmployeeTask", "assigned", "ready") is True

    def test_employee_task_submitted_to_peer_reviewing(self):
        assert can_transition("EmployeeTask", "submitted", "peer_reviewing") is True


# ── get_allowed_targets ────────────────────────────────────────────────


class TestGetAllowedTargets:
    def test_draft_targets(self):
        targets = get_allowed_targets("CompanyTask", "draft")
        assert "analyzing" in targets

    def test_unknown_entity_raises(self):
        with pytest.raises(ValueError, match="Unknown entity type"):
            get_allowed_targets("nonexistent", "state")

    def test_unknown_state_raises(self):
        with pytest.raises(ValueError, match="Unknown state"):
            get_allowed_targets("CompanyTask", "nonexistent")

    def test_completed_no_targets(self):
        targets = get_allowed_targets("CompanyTask", "completed")
        assert len(targets) == 0

    def test_draft_no_waiting_dependency(self):
        targets = get_allowed_targets("CompanyTask", "draft")
        assert "waiting_dependency" not in targets


# ── transition ─────────────────────────────────────────────────────────


class TestTransition:
    def test_valid_returns_none(self):
        result = transition("CompanyTask", "draft", "analyzing")
        assert result is None

    def test_invalid_raises(self):
        with pytest.raises(StateTransitionError):
            transition("CompanyTask", "completed", "draft")

    def test_waiting_to_failed(self):
        result = transition("CompanyTask", "waiting_dependency", "failed")
        assert result is None

    def test_paused_to_failed(self):
        result = transition("CompanyTask", "paused", "failed")
        assert result is None

    def test_draft_to_analyzing(self):
        result = transition("CompanyTask", "draft", "analyzing")
        assert result is None

    def test_analyzing_to_waiting_resource(self):
        result = transition("CompanyTask", "analyzing", "waiting_resource", resume_state="executing")
        assert result is None  # entering waiting state, resume_state stored

    def test_executing_to_reviewing(self):
        result = transition("CompanyTask", "executing", "reviewing")
        assert result is None

    def test_reviewing_to_completed(self):
        result = transition("CompanyTask", "final_review", "completed")
        assert result is None

    def test_executing_to_paused(self):
        result = transition("CompanyTask", "executing", "paused", resume_state="reviewing")
        assert result is None  # entering waiting state, resume_state stored

    def test_employee_task_assigned_to_ready(self):
        result = transition("EmployeeTask", "assigned", "ready")
        assert result is None

    def test_employee_task_running_to_submitted(self):
        result = transition("EmployeeTask", "running", "submitted")
        assert result is None


# ── validate_resume_state ──────────────────────────────────────────────


class TestValidateResumeState:
    def test_non_waiting_state_without_resume_ok(self):
        validate_resume_state("CompanyTask", "draft", None)

    def test_non_waiting_state_with_resume_raises(self):
        with pytest.raises(ValueError, match="resume_state must be null"):
            validate_resume_state("CompanyTask", "draft", "executing")

    def test_waiting_state_with_resume_accepted(self):
        validate_resume_state("CompanyTask", "waiting_dependency", "executing")

    def test_waiting_resource_requires_resume(self):
        with pytest.raises(ValueError, match="resume_state required"):
            validate_resume_state("CompanyTask", "waiting_resource", None)

    def test_waiting_permission_requires_resume(self):
        with pytest.raises(ValueError, match="resume_state required"):
            validate_resume_state("CompanyTask", "waiting_permission", None)

    def test_paused_requires_resume(self):
        with pytest.raises(ValueError, match="resume_state required"):
            validate_resume_state("CompanyTask", "paused", None)

    def test_waiting_approval_requires_resume(self):
        with pytest.raises(ValueError, match="resume_state required"):
            validate_resume_state("CompanyTask", "waiting_approval", None)
