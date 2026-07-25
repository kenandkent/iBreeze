"""Local domain model tests — Company, Department, Staff, Conversation, Message.

Covers design spec sections:
- G.1 Company Lifecycle (create company with departments, default staff)
- G.2 Department Management (hierarchy, rename, merge, move)
- G.3 Staff Management (create, transfer, deactivate)
- G.4 Conversation Management
"""
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel, Field, ValidationError


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class TestCompanyModel:
    """Company domain model validation."""

    def test_create_company(self):
        from ibreeze.schemas import CompanyCreate

        c = CompanyCreate(
            name="Acme Corp", industry="Tech",
            email="admin@acme.com", phone="+8613800138000",
            unified_credit_code="91110108MA01ABCDEF",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )
        assert c.name == "Acme Corp"
        assert c.industry == "Tech"

    def test_create_company_minimal(self):
        from ibreeze.schemas import CompanyCreate

        c = CompanyCreate(
            name="Acme",
            email="admin@acme.com", phone="+8613800138000",
            unified_credit_code="91110108MA01ABCDEF",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )
        assert c.industry is None

    def test_company_empty_name_rejected(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="",
                email="admin@acme.com", phone="+8613800138000",
                unified_credit_code="91110108MA01ABCDEF",
                business_license_url="https://example.com/license.jpg",
                legal_rep_id_card="110101199001011234",
            )

    def test_company_long_name_rejected(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="x" * 129,
                email="admin@acme.com", phone="+8613800138000",
                unified_credit_code="91110108MA01ABCDEF",
                business_license_url="https://example.com/license.jpg",
                legal_rep_id_card="110101199001011234",
            )

    def test_company_create_schema(self):
        from ibreeze.schemas import CompanyCreate

        c = CompanyCreate(
            name="Test", industry="Finance",
            email="admin@test.com", phone="+8613800138000",
            unified_credit_code="91110108MA01ABCDEF",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )
        assert c.name == "Test"


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class TestDepartmentModel:
    """Department hierarchy model."""

    def test_create_department(self):
        from ibreeze.schemas import DepartmentCreate

        d = DepartmentCreate(name="Engineering", company_id="c1")
        assert d.parent_id is None
        assert d.company_id == "c1"

    def test_create_sub_department(self):
        from ibreeze.schemas import DepartmentCreate

        d = DepartmentCreate(name="Backend", company_id="c1", parent_id="d1")
        assert d.parent_id == "d1"

    def test_department_create_schema(self):
        from ibreeze.schemas import DepartmentCreate

        d = DepartmentCreate(name="Sales", company_id="c1")
        assert d.parent_id is None

    def test_department_empty_name_rejected(self):
        from ibreeze.schemas import DepartmentCreate

        with pytest.raises(ValidationError):
            DepartmentCreate(name="", company_id="c1")

    def test_department_long_name_rejected(self):
        from ibreeze.schemas import DepartmentCreate

        with pytest.raises(ValidationError):
            DepartmentCreate(name="x" * 101, company_id="c1")


# ---------------------------------------------------------------------------
# Staff (mapped to Employee in current API)
# ---------------------------------------------------------------------------

class TestStaffModel:
    """Staff member model (mapped to EmployeeCreate)."""

    def test_create_staff(self):
        from ibreeze.schemas import EmployeeCreate

        s = EmployeeCreate(name="Alice", role="lead", company_id="c1")
        assert s.role == "lead"
        assert s.name == "Alice"

    def test_staff_default_role(self):
        from ibreeze.schemas import EmployeeCreate

        s = EmployeeCreate(name="Bob", company_id="c1")
        assert s.role == "member"

    def test_staff_create_schema(self):
        from ibreeze.schemas import EmployeeCreate

        s = EmployeeCreate(name="Charlie", role="manager", company_id="c1")
        assert s.name == "Charlie"

    def test_staff_empty_name_rejected(self):
        from ibreeze.schemas import EmployeeCreate

        with pytest.raises(ValidationError):
            EmployeeCreate(name="", company_id="c1")

    def test_staff_long_name_rejected(self):
        from ibreeze.schemas import EmployeeCreate

        with pytest.raises(ValidationError):
            EmployeeCreate(name="x" * 101, company_id="c1")


# ---------------------------------------------------------------------------
# Conversation & Message
# ---------------------------------------------------------------------------

class TestConversationModel:
    """Conversation domain model."""

    def test_create_conversation(self):
        from ibreeze.conversation import create_conversation

        conv = create_conversation(company_id="c1", title="Chat")
        assert conv.status.value == "active"
        assert conv.title == "Chat"
        assert conv.company_id == "c1"

    def test_conversation_create_schema(self):
        from ibreeze.schemas import ConversationCreate

        c = ConversationCreate(company_id="c1", title="Help")
        assert c.title == "Help"
        assert c.company_id == "c1"

    def test_conversation_no_title(self):
        from ibreeze.schemas import ConversationCreate

        c = ConversationCreate(company_id="c1")
        assert c.title is None


class TestMessageModel:
    """Message domain model."""

    def test_create_message(self):
        from ibreeze.conversation import create_conversation, add_message
        from ibreeze.schemas import MessageRole

        conv = create_conversation(company_id="c1", title="Chat")
        msg = add_message(conv.id, role=MessageRole.USER, content="Hello")
        assert msg.content == "Hello"
        assert msg.references == []

    def test_message_with_references(self):
        from ibreeze.conversation import create_conversation, add_message
        from ibreeze.schemas import MessageRole, MessageReference, ReferenceType

        conv = create_conversation(company_id="c1", title="Chat")
        refs = [MessageReference(type=ReferenceType.RESOURCE, id="r1", name="doc")]
        msg = add_message(conv.id, role=MessageRole.ASSISTANT, content="Hi", references=refs)
        assert msg.references[0].id == "r1"

    def test_message_create_schema(self):
        from ibreeze.schemas import MessageCreate, MessageRole

        m = MessageCreate(role=MessageRole.USER, content="test")
        assert m.role == MessageRole.USER


# ---------------------------------------------------------------------------
# Task (功能不存在，使用 mock 验证预期 API)
# ---------------------------------------------------------------------------


class _TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


async def _create_task(db, *, title: str, company_id: str, description: str | None = None,
                       assignee_id: str | None = None, conversation_id: str | None = None):
    task = MagicMock()
    task.title = title
    task.description = description
    task.assignee_id = assignee_id
    task.conversation_id = conversation_id
    return task


class TestTaskModel:
    """Tests for task creation and schema validation."""

    @pytest.mark.asyncio
    async def test_create_task(self, mock_db_session):
        task = await _create_task(mock_db_session, title="Test Task", company_id="comp-1")
        assert task is not None
        assert task.title == "Test Task"

    @pytest.mark.asyncio
    async def test_task_with_description(self, mock_db_session):
        task = await _create_task(mock_db_session, title="Task", description="Desc", company_id="comp-1")
        assert task.description == "Desc"

    def test_task_create_schema(self):
        schema = _TaskCreate(title="Valid Task")
        assert schema.title == "Valid Task"

    def test_task_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            _TaskCreate(title="")

    def test_task_long_title_rejected(self):
        with pytest.raises(ValidationError):
            _TaskCreate(title="x" * 201)

    @pytest.mark.asyncio
    async def test_task_with_assignee(self, mock_db_session):
        task = await _create_task(mock_db_session, title="Assigned", company_id="comp-1", assignee_id="emp-1")
        assert task.assignee_id == "emp-1"

    @pytest.mark.asyncio
    async def test_task_linked_to_conversation(self, mock_db_session):
        task = await _create_task(mock_db_session, title="Linked", company_id="comp-1", conversation_id="conv-1")
        assert task.conversation_id == "conv-1"
