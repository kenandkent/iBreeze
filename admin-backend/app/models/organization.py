from sqlalchemy import Column, String, JSON, func

from app.models.base import Base


class Company(Base):
    __tablename__ = "companies"

    company_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="initializing")
    default_provider_policy = Column(JSON, server_default="{}")
    default_budget_policy = Column(JSON, server_default="{}")
    root_department_id = Column(String)
    leader_employee_id = Column(String)
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))
    deleted_at = Column(String)
    dissolved_at = Column(String)


class Department(Base):
    __tablename__ = "departments"

    department_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    parent_id = Column(String)
    name = Column(String, nullable=False)
    description = Column(String)
    leader_employee_id = Column(String)
    status = Column(String, nullable=False, server_default="active")
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))
    deleted_at = Column(String)


class Employee(Base):
    __tablename__ = "employees"

    employee_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    department_id = Column(String)
    name = Column(String, nullable=False)
    role_name = Column(String)
    employee_type = Column(String, nullable=False, server_default="employee")
    template_id = Column(String)
    capability_snapshot = Column(JSON, server_default="{}")
    manager_id = Column(String)
    status = Column(String, nullable=False, server_default="active")
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))
    deleted_at = Column(String)


class AccessGrant(Base):
    __tablename__ = "access_grants"

    grant_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    employee_id = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    target_id = Column(String, nullable=False)
    permission = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="active")
    expires_at = Column(String, nullable=False)
    approved_by = Column(String, nullable=False)
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    revoked_at = Column(String)
