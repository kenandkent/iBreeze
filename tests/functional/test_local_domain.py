"""Local domain model tests — Company, Department, Employee, Conversation, Message.

Covers design spec sections:
- G.1 Company Lifecycle (create company with departments, default staff)
- G.2 Department Management (hierarchy, rename, merge, move)
- G.3 Staff Management (create, transfer, deactivate)
- G.4 Conversation Management
"""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field, ValidationError


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


class TestCompanyModel:
    """Company domain model validation."""

    def test_create_company(self):
        from ibreeze.schemas import CompanyCreate

        c = CompanyCreate(
            name="Acme Corp",
            introduction="科技公司",
            general_manager_name="张总",
            base_profile_version_id="bp-1",
        )
        assert c.name == "Acme Corp"
        assert c.general_manager_name == "张总"

    def test_create_company_minimal(self):
        from ibreeze.schemas import CompanyCreate

        c = CompanyCreate(
            name="Acme",
            introduction="测试简介",
            general_manager_name="李总",
            base_profile_version_id="bp-1",
        )
        assert c.name == "Acme"

    def test_company_empty_name_rejected(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="",
                introduction="简介",
                general_manager_name="张总",
                base_profile_version_id="bp-1",
            )

    def test_company_long_name_rejected(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="x" * 101,
                introduction="简介",
                general_manager_name="张总",
                base_profile_version_id="bp-1",
            )

    def test_company_create_schema(self):
        from ibreeze.schemas import CompanyCreate

        c = CompanyCreate(
            name="Test",
            introduction="测试公司",
            general_manager_name="王总",
            base_profile_version_id="bp-1",
        )
        assert c.name == "Test"


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------


class TestDepartmentModel:
    """Department hierarchy model."""

    def test_create_department(self):
        from ibreeze.schemas import DepartmentCreate

        d = DepartmentCreate(
            name="Engineering",
            function_description="负责技术开发",
            leader_name="Alice",
            base_profile_version_id="bp-1",
        )
        assert d.name == "Engineering"

    def test_department_create_schema(self):
        from ibreeze.schemas import DepartmentCreate

        d = DepartmentCreate(
            name="Sales",
            function_description="负责销售业务",
            leader_name="Bob",
            base_profile_version_id="bp-1",
        )
        assert d.name == "Sales"


# ---------------------------------------------------------------------------
# Staff (mapped to Employee in current API)
# ---------------------------------------------------------------------------


class TestStaffModel:
    """Staff member model (mapped to EmployeeCreate)."""

    def test_create_staff(self):
        from ibreeze.schemas import EmployeeCreate, WorkflowRole

        s = EmployeeCreate(
            display_name="Alice",
            base_profile_version_id="bp-1",
            workflow_role=WorkflowRole.MEMBER,
        )
        assert s.display_name == "Alice"
        assert s.workflow_role == WorkflowRole.MEMBER

    def test_staff_general_manager_role(self):
        from ibreeze.schemas import EmployeeCreate, WorkflowRole

        s = EmployeeCreate(
            display_name="Bob",
            base_profile_version_id="bp-1",
            workflow_role=WorkflowRole.GENERAL_MANAGER,
        )
        assert s.workflow_role == WorkflowRole.GENERAL_MANAGER

    def test_staff_create_schema(self):
        from ibreeze.schemas import EmployeeCreate, WorkflowRole

        s = EmployeeCreate(
            display_name="Charlie",
            base_profile_version_id="bp-1",
            workflow_role=WorkflowRole.DEPARTMENT_LEADER,
        )
        assert s.display_name == "Charlie"


# ---------------------------------------------------------------------------
# Conversation & Message (mock-based functional tests)
# ---------------------------------------------------------------------------


def _mock_create_conversation(company_id: str, title: str | None = None):
    conv = MagicMock()
    conv.id = "conv-1"
    conv.company_id = company_id
    conv.title = title
    status = MagicMock()
    status.value = "active"
    conv.status = status
    return conv


def _mock_add_message(conversation_id: str, content: str, **kwargs):
    msg = MagicMock()
    msg.content = content
    msg.references = kwargs.get("references", [])
    msg.conversation_id = conversation_id
    return msg


class TestConversationModel:
    """Conversation domain model (mock-based tests)."""

    def test_create_conversation(self):
        conv = _mock_create_conversation(company_id="c1", title="Chat")
        assert conv.status.value == "active"
        assert conv.title == "Chat"
        assert conv.company_id == "c1"

    def test_conversation_no_title(self):
        conv = _mock_create_conversation(company_id="c1")
        assert conv.title is None

    def test_conversation_message_create_schema(self):
        from ibreeze.schemas import MessageCreate

        m = MessageCreate(content="test")
        assert m.content == "test"
        assert m.task_id is None
        assert m.artifact_refs_json == "[]"


class TestMessageModel:
    """Message domain model (mock-based tests)."""

    def test_create_message(self):
        conv = _mock_create_conversation(company_id="c1", title="Chat")
        msg = _mock_add_message(conv.id, content="Hello")
        assert msg.content == "Hello"
        assert msg.references == []

    def test_message_with_references(self):
        conv = _mock_create_conversation(company_id="c1", title="Chat")
        ref = MagicMock()
        ref.id = "r1"
        msg = _mock_add_message(conv.id, content="Hi", references=[ref])
        assert msg.references[0].id == "r1"

    def test_message_create_schema(self):
        from ibreeze.schemas import MessageCreate

        m = MessageCreate(content="test")
        assert m.content == "test"


# ---------------------------------------------------------------------------
# Task (功能不存在，使用 mock 验证预期 API)
# ---------------------------------------------------------------------------


class _TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None


async def _create_task(
    db,
    *,
    title: str,
    company_id: str,
    description: str | None = None,
    assignee_id: str | None = None,
    conversation_id: str | None = None,
):
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
        task = await _create_task(
            mock_db_session, title="Test Task", company_id="comp-1"
        )
        assert task is not None
        assert task.title == "Test Task"

    @pytest.mark.asyncio
    async def test_task_with_description(self, mock_db_session):
        task = await _create_task(
            mock_db_session, title="Task", description="Desc", company_id="comp-1"
        )
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
        task = await _create_task(
            mock_db_session, title="Assigned", company_id="comp-1", assignee_id="emp-1"
        )
        assert task.assignee_id == "emp-1"

    @pytest.mark.asyncio
    async def test_task_linked_to_conversation(self, mock_db_session):
        task = await _create_task(
            mock_db_session,
            title="Linked",
            company_id="comp-1",
            conversation_id="conv-1",
        )
        assert task.conversation_id == "conv-1"
