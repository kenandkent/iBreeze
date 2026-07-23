"""Schema validation tests – aligned with design doc."""
import pytest
from datetime import datetime
from pydantic import ValidationError
from ibreeze.schemas import (
    CompanyCreate,
    CompanyUpdate,
    ConversationCreate,
    ConversationUpdate,
    ConversationStatus,
    MessageCreate,
    MessageRole,
    KnowledgeEntryCreate,
    KnowledgeType,
    WorkspaceCreate,
    OrchestrationCreate,
    EmployeeCreate,
    DepartmentCreate,
    AuditEventCreate,
    AuditOutcome,
    PaginationParams,
    PaginatedResponse,
)


def test_company_create_valid():
    """Test valid company creation schema."""
    company = CompanyCreate(
        name="Test",
        introduction="A test company",
    )
    assert company.name == "Test"
    assert company.introduction == "A test company"


def test_company_create_missing_name():
    """Test company creation without name."""
    with pytest.raises(ValidationError):
        CompanyCreate(introduction="Some intro")


def test_company_create_missing_introduction():
    """Test company creation without introduction."""
    with pytest.raises(ValidationError):
        CompanyCreate(name="Test")


def test_company_update_partial():
    """Test partial company update."""
    update = CompanyUpdate(name="New Name")
    assert update.name == "New Name"
    assert update.introduction is None
    assert update.expected_version is None


def test_conversation_create():
    """Test conversation creation schema."""
    conv = ConversationCreate(company_id="company-123", title="Test")
    assert conv.company_id == "company-123"
    assert conv.title == "Test"


def test_conversation_update_status():
    """Test conversation status update."""
    update = ConversationUpdate(status=ConversationStatus.ARCHIVED)
    assert update.status == ConversationStatus.ARCHIVED


def test_message_create():
    """Test message creation schema."""
    msg = MessageCreate(role=MessageRole.USER, content="Hello")
    assert msg.role == MessageRole.USER
    assert msg.content == "Hello"


def test_knowledge_entry_create():
    """Test knowledge entry creation schema."""
    entry = KnowledgeEntryCreate(
        title="FAQ",
        content="This is a FAQ",
        type=KnowledgeType.FAQ,
    )
    assert entry.title == "FAQ"
    assert entry.type == KnowledgeType.FAQ


def test_workspace_create():
    """Test workspace creation schema."""
    ws = WorkspaceCreate(name="Test Workspace", company_id="company-123")
    assert ws.name == "Test Workspace"
    assert ws.company_id == "company-123"


def test_orchestration_create():
    """Test orchestration creation schema."""
    orch = OrchestrationCreate(name="Test Orchestration", company_id="company-123")
    assert orch.name == "Test Orchestration"
    assert orch.company_id == "company-123"


def test_employee_create():
    """Test employee creation schema."""
    emp = EmployeeCreate(name="John Doe", company_id="company-123")
    assert emp.name == "John Doe"
    assert emp.company_id == "company-123"


def test_department_create():
    """Test department creation schema."""
    dept = DepartmentCreate(name="Engineering", company_id="company-123")
    assert dept.name == "Engineering"
    assert dept.company_id == "company-123"


def test_audit_event_create():
    """Test audit event creation schema."""
    event = AuditEventCreate(
        event_type="user.login",
        actor_type="user",
        resource_type="auth",
        outcome=AuditOutcome.SUCCESS,
    )
    assert event.event_type == "user.login"
    assert event.outcome == AuditOutcome.SUCCESS


def test_pagination_params():
    """Test pagination parameters."""
    params = PaginationParams(cursor="abc", limit=20)
    assert params.cursor == "abc"
    assert params.limit == 20


def test_pagination_params_defaults():
    """Test pagination parameters defaults."""
    params = PaginationParams()
    assert params.cursor is None
    assert params.limit == 50


def test_pagination_params_validation():
    """Test pagination parameters validation."""
    with pytest.raises(ValidationError):
        PaginationParams(limit=0)
    with pytest.raises(ValidationError):
        PaginationParams(limit=201)


def test_paginated_response():
    """Test paginated response schema."""
    response = PaginatedResponse(items=[1, 2, 3], next_cursor="xyz", has_more=True)
    assert response.items == [1, 2, 3]
    assert response.next_cursor == "xyz"
    assert response.has_more is True


def test_strict_model_forbids_extra():
    """Test that StrictModel forbids extra fields."""
    from ibreeze.schemas import StrictModel

    class TestModel(StrictModel):
        name: str

    with pytest.raises(ValidationError):
        TestModel(name="test", extra="not allowed")
