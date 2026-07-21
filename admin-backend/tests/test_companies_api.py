import pytest
from httpx import AsyncClient

from app.models.organization import Company, Department, Employee


@pytest.fixture
async def seed_org(db_session):
    company = Company(
        company_id="comp-1",
        name="Test Corp",
        status="active",
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    dept = Department(
        department_id="dept-1",
        company_id="comp-1",
        name="Engineering",
        status="active",
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    emp = Employee(
        employee_id="emp-1",
        company_id="comp-1",
        department_id="dept-1",
        name="Alice",
        employee_type="employee",
        status="active",
        version="1",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    db_session.add_all([company, dept, emp])
    await db_session.commit()


@pytest.mark.usefixtures("seed_org")
class TestCompaniesAPI:
    async def test_list_companies(self, client: AsyncClient):
        resp = await client.get("/api/companies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["company_id"] == "comp-1"

    async def test_get_company(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Corp"

    async def test_get_company_not_found(self, client: AsyncClient):
        resp = await client.get("/api/companies/nonexistent")
        assert resp.status_code == 404

    async def test_list_departments(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1/departments")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_department(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1/departments/dept-1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Engineering"

    async def test_get_department_not_found(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1/departments/nonexistent")
        assert resp.status_code == 404

    async def test_list_employees(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1/employees")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_get_employee(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1/employees/emp-1")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Alice"

    async def test_get_employee_not_found(self, client: AsyncClient):
        resp = await client.get("/api/companies/comp-1/employees/nonexistent")
        assert resp.status_code == 404
