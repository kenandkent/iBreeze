"""Company domain service tests."""
import pytest
from ibreeze.company import (
    create_company,
    list_companies,
    get_company,
    update_company,
    delete_company,
)
from ibreeze.schemas import CompanyCreate, CompanyUpdate
from pydantic import ValidationError


@pytest.fixture
def sample_company_data():
    """Sample company creation data."""
    return CompanyCreate(
        name="Test Company",
        email="test@company.com",
        phone="+8613800138000",
        unified_credit_code="123456789012345678",
        business_license_url="https://example.com/license.jpg",
        legal_rep_id_card="110101199001011234",
        industry="Technology",
    )


def test_create_company(sample_company_data):
    """Test creating a company."""
    company = create_company(sample_company_data)
    assert company.name == "Test Company"
    assert company.email == "test@company.com"
    assert company.phone == "+8613800138000"
    assert company.unified_credit_code == "123456789012345678"
    assert company.business_license_url == "https://example.com/license.jpg"
    assert company.legal_rep_id_card == "110101199001011234"
    assert company.industry == "Technology"
    assert company.is_deleted is False
    assert company.id is not None


def test_list_companies(sample_company_data):
    """Test listing companies."""
    create_company(sample_company_data)
    companies = list_companies()
    assert len(companies) >= 1


def test_get_company(sample_company_data):
    """Test getting a company by ID."""
    company = create_company(sample_company_data)
    fetched = get_company(company.id)
    assert fetched.id == company.id
    assert fetched.name == "Test Company"


def test_get_company_not_found():
    """Test getting a non-existent company."""
    with pytest.raises(KeyError):
        get_company("nonexistent-id")


def test_update_company(sample_company_data):
    """Test updating a company."""
    company = create_company(sample_company_data)
    update_data = CompanyUpdate(name="Updated Company")
    updated = update_company(company.id, update_data)
    assert updated.name == "Updated Company"
    assert updated.email == "test@company.com"


def test_delete_company(sample_company_data):
    """Test soft deleting a company."""
    company = create_company(sample_company_data)
    delete_company(company.id)
    with pytest.raises(KeyError):
        get_company(company.id)


def test_delete_company_not_found():
    """Test deleting a non-existent company."""
    with pytest.raises(KeyError):
        delete_company("nonexistent-id")


def test_company_phone_validation():
    """Test phone number validation (E.164 format)."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="1234567890",  # Invalid format
            unified_credit_code="123456789012345678",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )


def test_company_credit_code_validation():
    """Test unified credit code validation (18 alphanumeric)."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="+8613800138000",
            unified_credit_code="12345678901234567",  # 17 digits
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
        )


def test_company_id_card_validation():
    """Test ID card validation (18 digits)."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="+8613800138000",
            unified_credit_code="123456789012345678",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="12345678901234567",  # 17 digits
        )


def test_company_license_url_validation():
    """Test business license URL validation (must start with http/https)."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="+8613800138000",
            unified_credit_code="123456789012345678",
            business_license_url="ftp://example.com/license.jpg",  # Invalid scheme
            legal_rep_id_card="110101199001011234",
        )


def test_company_extra_fields_forbidden():
    """Test that extra fields are forbidden in company schema."""
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="Test",
            email="test@test.com",
            phone="+8613800138000",
            unified_credit_code="123456789012345678",
            business_license_url="https://example.com/license.jpg",
            legal_rep_id_card="110101199001011234",
            extra_field="not allowed",  # type: ignore
        )
