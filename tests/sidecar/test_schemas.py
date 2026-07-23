"""Sidecar schema validation tests — Company, Conversation, Knowledge schemas.

Covers design spec sections:
- H.1 Schema validation (Pydantic V2 strict models)
"""
import pytest
from pydantic import ValidationError


class TestCompanySchemas:
    """Company schema validation."""

    def test_company_create_valid(self):
        from ibreeze.schemas import CompanyCreate

        company = CompanyCreate(
            name="Acme Corp",
            email="admin@acme.com",
            phone="+8613800138000",
            unified_credit_code="91110108MA01ABCDEF",
            business_license_url="https://example.com/license.pdf",
            legal_rep_id_card="110101199001011234",
        )
        assert company.name == "Acme Corp"
        assert company.unified_credit_code == "91110108MA01ABCDEF"

    def test_company_create_invalid_email(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="Acme",
                email="not-an-email",
                phone="+8613800138000",
                unified_credit_code="91110108MA01ABCDEF",
                business_license_url="https://example.com/license.pdf",
                legal_rep_id_card="110101199001011234",
            )

    def test_company_create_invalid_phone(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="Acme",
                email="admin@acme.com",
                phone="12345",
                unified_credit_code="91110108MA01ABCDEF",
                business_license_url="https://example.com/license.pdf",
                legal_rep_id_card="110101199001011234",
            )

    def test_company_create_invalid_credit_code(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="Acme",
                email="admin@acme.com",
                phone="+8613800138000",
                unified_credit_code="SHORT",
                business_license_url="https://example.com/license.pdf",
                legal_rep_id_card="110101199001011234",
            )

    def test_company_create_invalid_id_card(self):
        from ibreeze.schemas import CompanyCreate

        with pytest.raises(ValidationError):
            CompanyCreate(
                name="Acme",
                email="admin@acme.com",
                phone="+8613800138000",
                unified_credit_code="91110108MA01ABCDEF",
                business_license_url="https://example.com/license.pdf",
                legal_rep_id_card="12345",
            )


class TestConversationSchemas:
    """Conversation schema validation."""

    def test_conversation_create_valid(self):
        from ibreeze.schemas import ConversationCreate

        conv = ConversationCreate(company_id="c1", title="Help")
        assert conv.company_id == "c1"
        assert conv.title == "Help"

    def test_message_role_enum(self):
        from ibreeze.schemas import MessageRole

        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.TOOL == "tool"


class TestKnowledgeSchemas:
    """Knowledge entry schema validation."""

    def test_knowledge_entry_create_valid(self):
        from ibreeze.schemas import KnowledgeEntryCreate, KnowledgeType

        entry = KnowledgeEntryCreate(
            title="FAQ",
            content="What is iBreeze?",
            type=KnowledgeType.FAQ,
            tags=["intro"],
        )
        assert entry.title == "FAQ"
        assert entry.type == KnowledgeType.FAQ

    def test_knowledge_entry_type_enum(self):
        from ibreeze.schemas import KnowledgeType

        assert KnowledgeType.FAQ == "FAQ"
        assert KnowledgeType.DOC == "DOC"
        assert KnowledgeType.URL == "URL"
