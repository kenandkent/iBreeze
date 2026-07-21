from pydantic import BaseModel


class CompanyResponse(BaseModel):
    company_id: str
    name: str
    status: str
    root_department_id: str | None = None
    leader_employee_id: str | None = None
    version: str
    created_at: str
    updated_at: str


class DepartmentResponse(BaseModel):
    department_id: str
    company_id: str
    parent_id: str | None = None
    name: str
    description: str | None = None
    leader_employee_id: str | None = None
    status: str
    version: str
    created_at: str
    updated_at: str


class EmployeeResponse(BaseModel):
    employee_id: str
    company_id: str
    department_id: str | None = None
    name: str
    role_name: str | None = None
    employee_type: str
    template_id: str | None = None
    manager_id: str | None = None
    status: str
    version: str
    created_at: str
    updated_at: str
