"""Compatibility rule tests — CRUD, evaluation logic, priority, deny overrides.

Covers design spec sections:
- G.5 Compatibility rules evaluation
"""
import uuid
from unittest.mock import MagicMock

import pytest


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_count_result(count):
    r = MagicMock()
    r.scalar.return_value = count
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


class TestCompatibilityRule:
    """Compatibility rule service CRUD and evaluation."""

    @pytest.mark.asyncio
    async def test_create_compatibility_rule(self, mock_db_session):
        from ibreeze_backend.compatibility.service import create_rule

        rule = await create_rule(
            mock_db_session,
            subject_type="agent",
            subject_version_range={"min": "1.0"},
            dependency_type="model",
            dependency_version_range=None,
            result="allow",
            reason_code=None,
            priority=10,
        )
        assert rule.subject_type == "agent"
        assert rule.result == "allow"
        assert rule.priority == 10
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_compatibility_rules(self, mock_db_session):
        from ibreeze_backend.compatibility.service import list_rules

        rule1 = MagicMock()
        rule2 = MagicMock()

        count_result = _mock_count_result(2)
        list_result = _mock_scalars([rule1, rule2])

        mock_db_session.execute.side_effect = [count_result, list_result]

        rules, total = await list_rules(mock_db_session, skip=0, limit=10)
        assert total == 2
        assert len(rules) == 2

    @pytest.mark.asyncio
    async def test_evaluate_compatibility_allow(self, mock_db_session):
        from ibreeze_backend.compatibility.service import evaluate

        mock_db_session.execute.return_value = _mock_scalars([])

        result, reason, rule_id = await evaluate(
            mock_db_session, "agent", "1.0", "model", "1.0"
        )
        assert result == "allow"
        assert reason is None
        assert rule_id is None

    @pytest.mark.asyncio
    async def test_evaluate_compatibility_deny(self, mock_db_session):
        from ibreeze_backend.compatibility.service import evaluate

        rule = MagicMock()
        rule.id = uuid.uuid4()
        rule.result = "deny"
        rule.reason_code = "INCOMPATIBLE"
        rule.priority = 10
        rule.subject_version_range = None
        rule.dependency_version_range = None

        mock_db_session.execute.return_value = _mock_scalars([rule])

        result, reason, rule_id = await evaluate(
            mock_db_session, "agent", "1.0", "model", "1.0"
        )
        assert result == "deny"
        assert reason == "INCOMPATIBLE"
        assert rule_id == str(rule.id)

    @pytest.mark.asyncio
    async def test_evaluate_compatibility_deny_overrides_allow(self, mock_db_session):
        from ibreeze_backend.compatibility.service import evaluate

        allow_rule = MagicMock()
        allow_rule.id = uuid.uuid4()
        allow_rule.result = "allow"
        allow_rule.reason_code = None
        allow_rule.priority = 10
        allow_rule.subject_version_range = None
        allow_rule.dependency_version_range = None

        deny_rule = MagicMock()
        deny_rule.id = uuid.uuid4()
        deny_rule.result = "deny"
        deny_rule.reason_code = "BLOCKED"
        deny_rule.priority = 10
        deny_rule.subject_version_range = None
        deny_rule.dependency_version_range = None

        mock_db_session.execute.return_value = _mock_scalars([allow_rule, deny_rule])

        result, reason, rule_id = await evaluate(
            mock_db_session, "agent", "1.0", "model", "1.0"
        )
        assert result == "deny"
        assert reason == "BLOCKED"

    @pytest.mark.asyncio
    async def test_evaluate_compatibility_fallback(self, mock_db_session):
        from ibreeze_backend.compatibility.service import evaluate

        mock_db_session.execute.return_value = _mock_scalars([])

        result, reason, rule_id = await evaluate(
            mock_db_session, "agent", "1.0", "tool", "1.0"
        )
        assert result == "allow"

    @pytest.mark.asyncio
    async def test_evaluate_compatibility_no_rule_default_allow(self, mock_db_session):
        from ibreeze_backend.compatibility.service import evaluate

        mock_db_session.execute.return_value = _mock_scalars([])

        result, reason, rule_id = await evaluate(
            mock_db_session, "nonexistent", None, "nonexistent", None
        )
        assert result == "allow"
        assert reason is None

    @pytest.mark.asyncio
    async def test_disable_rule(self, mock_db_session):
        from ibreeze_backend.compatibility.service import delete_rule

        rule = MagicMock()
        mock_db_session.execute.return_value = _mock_result(rule)

        await delete_rule(mock_db_session, uuid.uuid4())
        mock_db_session.delete.assert_awaited_once_with(rule)
        mock_db_session.flush.assert_awaited_once()


class TestVersionInRange:
    """Version range checking logic."""

    def test_no_range_returns_true(self):
        from ibreeze_backend.compatibility.service import _version_in_range

        assert _version_in_range("1.0", None) is True
        assert _version_in_range(None, None) is True

    def test_within_range(self):
        from ibreeze_backend.compatibility.service import _version_in_range

        assert _version_in_range("1.5", {"min": "1.0", "max": "2.0"}) is True

    def test_below_min(self):
        from ibreeze_backend.compatibility.service import _version_in_range

        assert _version_in_range("0.9", {"min": "1.0", "max": "2.0"}) is False

    def test_at_max(self):
        from ibreeze_backend.compatibility.service import _version_in_range

        assert _version_in_range("2.0", {"min": "1.0", "max": "2.0"}) is False
