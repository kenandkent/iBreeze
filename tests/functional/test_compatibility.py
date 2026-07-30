"""Compatibility rule tests — CRUD, priority.

Covers design spec sections:
- G.5 Compatibility rules CRUD
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestRuleSchemas:
    """Pydantic schema validation for compatibility rules."""

    def test_rule_create_valid(self):
        from ibreeze_backend.compatibility.schemas import RuleCreate

        body = RuleCreate(
            subject_type="agent",
            subject_id=uuid.uuid4(),
            subject_version_range=">=1.0.0",
            dependency_type="model",
            dependency_key="gpt-4",
            dependency_version_range="*",
            decision="allow",
            reason_code="standard",
            priority=10,
        )
        assert body.subject_type == "agent"
        assert body.decision == "allow"

    def test_rule_create_invalid_subject_type_rejected(self):
        from ibreeze_backend.compatibility.schemas import RuleCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RuleCreate(
                subject_type="bad",
                subject_id=uuid.uuid4(),
                subject_version_range=">=1.0.0",
                dependency_type="model",
                dependency_key="gpt-4",
                dependency_version_range="*",
                decision="allow",
                reason_code="standard",
                priority=10,
            )

    def test_rule_create_empty_version_range_rejected(self):
        from ibreeze_backend.compatibility.schemas import RuleCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RuleCreate(
                subject_type="agent",
                subject_id=uuid.uuid4(),
                subject_version_range="",
                dependency_type="model",
                dependency_key="gpt-4",
                dependency_version_range="*",
                decision="allow",
                reason_code="standard",
                priority=10,
            )


# ---------------------------------------------------------------------------
# Compatibility service
# ---------------------------------------------------------------------------


class TestCompatibilityRule:
    """Compatibility rule service CRUD."""

    @pytest.mark.asyncio
    async def test_create_rule(self, mock_db_session):
        from ibreeze_backend.compatibility.schemas import RuleCreate
        from ibreeze_backend.compatibility.service import create_rule

        body = RuleCreate(
            subject_type="agent",
            subject_id=uuid.uuid4(),
            subject_version_range=">=1.0.0",
            dependency_type="model",
            dependency_key="gpt-4",
            dependency_version_range="*",
            decision="allow",
            reason_code="standard",
            priority=10,
        )
        rule = await create_rule(mock_db_session, body)
        assert rule.subject_type == "agent"
        assert rule.decision == "allow"
        assert rule.priority == 10
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_rules(self, mock_db_session):
        from ibreeze_backend.compatibility.service import list_rules

        mock_db_session.scalars = AsyncMock(return_value=["r1", "r2"])
        rules = await list_rules(mock_db_session, limit=10)
        assert len(rules) == 2

    @pytest.mark.asyncio
    async def test_get_rule_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.compatibility.service import get_rule

        mock_db_session.execute.return_value = mock_scalar_result("rule")
        result = await get_rule(mock_db_session, uuid.uuid4())
        assert result == "rule"

    @pytest.mark.asyncio
    async def test_get_rule_not_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.compatibility.service import get_rule

        mock_db_session.execute.return_value = mock_scalar_result(None)
        result = await get_rule(mock_db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_rule(self, mock_db_session):
        from ibreeze_backend.compatibility.service import delete_rule

        rule = MagicMock()
        rule.id = uuid.uuid4()
        rule.status = "draft"
        rule.version = 1

        with patch(
            "ibreeze_backend.compatibility.service._locked_rule",
            new_callable=AsyncMock,
            return_value=rule,
        ):
            await delete_rule(mock_db_session, rule.id, expected_version=1)
            mock_db_session.delete.assert_awaited_once_with(rule)
            mock_db_session.flush.assert_awaited_once()
