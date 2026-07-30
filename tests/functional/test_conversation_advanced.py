"""Tests for conversation message projection.

Covers design spec sections:
- CONV-001 Company scope enforcement
- CONV-002 Message projection rebuildable from events
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
class TestConversationAdvanced:
    """Conversation advanced scenario tests."""

    async def test_message_projection_rebuild(self):
        """CONV-002: Message projection should be rebuildable from events."""
        from ibreeze.conversation import list_messages

        db = AsyncMock()
        msg_row = {
            "id": str(uuid.uuid4()),
            "company_id": "c1",
            "conversation_id": "conv1",
            "task_id": "task1",
            "source_event_id": "evt1",
            "sender_type": "user",
            "sender_employee_id": None,
            "message_type": "user_message",
            "content": "Hello",
            "artifact_refs_json": "[]",
            "created_at": "2025-01-01T00:00:00Z",
        }
        cursor = AsyncMock()
        cursor.fetchall.return_value = [msg_row]
        db.execute.return_value = cursor

        messages = await list_messages(db, "c1", "conv1")
        assert len(messages) == 1
        assert messages[0].content == "Hello"
        assert messages[0].conversation_id == "conv1"

    async def test_company_scope_enforcement(self):
        """CONV-001: Messages must belong to correct company scope."""
        from ibreeze.conversation import submit_user_message
        from ibreeze.schemas import SubmitUserMessageRequest

        db = AsyncMock()
        scope_row = {
            "company_status": "active",
            "conversation_type": "company",
            "department_id": None,
        }
        cursor = AsyncMock()
        cursor.fetchone.return_value = scope_row
        cursor.fetchall.return_value = []
        db.execute.return_value = cursor
        db.commit = AsyncMock()

        data = SubmitUserMessageRequest(
            company_id="c1",
            conversation_id="conv1",
            content="Test message",
        )
        result = await submit_user_message(db, data)
        assert result.company_task_id is not None
        assert result.task_status == "draft"

    async def test_submit_user_message_target_task(self):
        """Submit with target_task_id should create plan_revision."""
        from ibreeze.conversation import submit_user_message
        from ibreeze.schemas import SubmitUserMessageRequest

        db = AsyncMock()
        scope_row = {
            "company_status": "active",
            "conversation_type": "company",
            "department_id": None,
        }
        task_row = {
            "id": "task1",
            "status": "awaiting_user_confirmation",
            "version": 2,
        }

        call_count = [0]

        async def mock_execute(sql, params=()):
            call_count[0] += 1
            cursor = MagicMock()
            cursor.fetchone = AsyncMock()
            cursor.fetchall = AsyncMock(return_value=[])
            # call 1: BEGIN IMMEDIATE, call 2: scope query, call 3: task query
            if call_count[0] == 1:
                cursor.fetchone.return_value = None
            elif call_count[0] == 2:
                cursor.fetchone.return_value = scope_row
            elif call_count[0] == 3:
                cursor.fetchone.return_value = task_row
            else:
                cursor.fetchone.return_value = None
                cursor.lastrowid = 1
            return cursor

        db.execute = mock_execute
        db.commit = AsyncMock()

        data = SubmitUserMessageRequest(
            company_id="c1",
            conversation_id="conv1",
            content="Revision",
            target_task_id="task1",
        )
        result = await submit_user_message(db, data)
        assert result.intake_mode == "plan_revision"
        assert result.task_status == "revision_requested"

    async def test_submit_user_message_company_archived_rejected(self):
        """Archived company should reject messages."""
        from ibreeze.conversation import submit_user_message
        from ibreeze.schemas import SubmitUserMessageRequest

        db = AsyncMock()
        scope_row = {
            "company_status": "archived",
            "conversation_type": "company",
            "department_id": None,
        }
        cursor = AsyncMock()
        cursor.fetchone.return_value = scope_row
        db.execute.return_value = cursor

        data = SubmitUserMessageRequest(
            company_id="c1",
            conversation_id="conv1",
            content="Test",
        )
        with pytest.raises(ValueError, match="COMPANY_ARCHIVED"):
            await submit_user_message(db, data)

    async def test_list_messages_empty(self):
        """Empty conversation should return empty list."""
        from ibreeze.conversation import list_messages

        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall.return_value = []
        db.execute.return_value = cursor

        messages = await list_messages(db, "c1", "conv-empty")
        assert messages == []
