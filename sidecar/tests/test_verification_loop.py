"""Tests for ibreeze.runtime.verification_loop module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.runtime.verification_loop import MAX_FIX_ATTEMPTS, verify_and_fix


class TestVerifyAndFix:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchone = MagicMock(return_value=None)
        cursor.fetchall = MagicMock(return_value=[])
        db.execute = AsyncMock(return_value=cursor)
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def mock_supervisor(self):
        sup = AsyncMock()
        sup.start = AsyncMock()
        sup.wait = AsyncMock(return_value={"exit_code": 0, "stdout_preview": ""})
        return sup

    async def test_verification_passes_on_first_attempt(self, mock_db, mock_supervisor):
        with patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor):
            result = await verify_and_fix(
                mock_db,
                run_id="run-1",
                company_id="company-1",
                artifact_id="artifact-1",
                verification_command="pytest",
                cwd="/tmp",
            )

            assert result["status"] == "passed"
            assert result["attempts"] == 1
            assert len(result["results"]) == 1
            assert result["results"][0]["exit_code"] == 0
            assert result["results"][0]["output_preview"] == ""

    async def test_verification_fails_then_passes(self, mock_db, mock_supervisor):
        call_count = 0

        async def mock_wait(run_id, timeout):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"exit_code": 1, "stdout_preview": "error"}
            return {"exit_code": 0, "stdout_preview": "passed"}

        mock_supervisor.wait = mock_wait

        with patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor):
            result = await verify_and_fix(
                mock_db,
                run_id="run-2",
                company_id="company-2",
                artifact_id="artifact-2",
                verification_command="make test",
            )

            assert result["status"] == "passed"
            assert result["attempts"] == 3
            assert len(result["results"]) == 3

    async def test_verification_fails_all_attempts(self, mock_db, mock_supervisor):
        mock_supervisor.wait = AsyncMock(
            return_value={
                "exit_code": 1,
                "stdout_preview": "failure",
            }
        )

        with patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor):
            result = await verify_and_fix(
                mock_db,
                run_id="run-3",
                company_id="company-3",
                artifact_id="artifact-3",
                verification_command="failing-cmd",
            )

            assert result["status"] == "failed"
            assert result["attempts"] == MAX_FIX_ATTEMPTS
            assert len(result["results"]) == MAX_FIX_ATTEMPTS

    async def test_verification_writes_results_to_db(self, mock_db, mock_supervisor):
        with patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor):
            await verify_and_fix(
                mock_db,
                run_id="run-4",
                company_id="company-4",
                artifact_id="artifact-4",
                verification_command="test",
            )

            mock_db.execute.assert_called()
            insert_call = mock_db.execute.call_args_list[0]
            assert "INSERT INTO verification_results" in insert_call[0][0]

    async def test_verification_uses_cwd(self, mock_db, mock_supervisor):
        with patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor):
            await verify_and_fix(
                mock_db,
                run_id="run-5",
                company_id="company-5",
                artifact_id="artifact-5",
                verification_command="ls",
                cwd="/workspace",
            )

            call_kwargs = mock_supervisor.start.call_args
            assert call_kwargs[1].get("cwd") == "/workspace" or call_kwargs.kwargs.get("cwd") == "/workspace"

    async def test_verification_splits_command(self, mock_db, mock_supervisor):
        with patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor):
            await verify_and_fix(
                mock_db,
                run_id="run-6",
                company_id="company-6",
                artifact_id="artifact-6",
                verification_command="pytest -v --tb=short",
            )

            call_args = mock_supervisor.start.call_args
            assert call_args[0][1] == ["pytest", "-v", "--tb=short"]

    async def test_verification_projects_outcome_when_routed(self, mock_db, mock_supervisor):
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"id": "decision-1"})
        mock_db.execute = AsyncMock(side_effect=[MagicMock(), cursor])
        with (
            patch("ibreeze.runtime.process_supervisor.get_supervisor", return_value=mock_supervisor),
            patch("ibreeze.routing.outcomes.RouteOutcomeProjector.append", new_callable=AsyncMock) as append,
        ):
            await verify_and_fix(
                mock_db,
                run_id="run-routed",
                company_id="company-routed",
                artifact_id="artifact-routed",
                verification_command="pytest",
            )
        append.assert_awaited_once()
        assert append.call_args.kwargs["route_decision_id"] == "decision-1"
        assert append.call_args.kwargs["outcome_type"] == "verification"
