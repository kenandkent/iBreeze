"""Schema validation tests."""
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
        email="test@test.com",
        phone="+8613800138000",
        unified_credit_code="123456789012345678",
        business_license_url="https://example.com/license.jpg",
        legal_rep_id_card="110101199001011234",
    )
    assert company.name == "Test"


def test_company_create_invalid_phone():
    """Test company creation with invalid phone."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="1234567890",
            unified_credit_code="123456789012345678",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )


def test_company_create_invalid_credit_code():
    """Test company creation with invalid credit code."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="+8613800138000",
            unified_credit_code="12345678901234567",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )


def test_company_update_partial():
    """Test partial company update."""
    update = CompanyUpdate(name="New Name")
    assert update.name == "New Name"
    assert update.email is None


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
    params = PaginationParams(offset=10, limit=20)
    assert params.offset == 10
    assert params.limit == 20


def test_pagination_params_defaults():
    """Test pagination parameters defaults."""
    params = PaginationParams()
    assert params.offset == 0
    assert params.limit == 20


def test_pagination_params_validation():
    """Test pagination parameters validation."""
    with pytest.raises(ValidationError):
        PaginationParams(offset=-1)
    with pytest.raises(ValidationError):
        PaginationParams(limit=0)
    with pytest.raises(ValidationError):
        PaginationParams(limit=101)


def test_paginated_response():
    """Test paginated response schema."""
    response = PaginatedResponse(total=100, offset=0, limit=20)
    assert response.total == 100
    assert response.offset == 0
    assert response.limit == 20


def test_strict_model_forbids_extra():
    """Test that StrictModel forbids extra fields."""
    from ibreeze.schemas import StrictModel

    class TestModel(StrictModel):
        name: str

    with pytest.raises(ValidationError):
        TestModel(name="test", extra="not allowed")
