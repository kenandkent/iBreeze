from sqlalchemy import Column, String, JSON, func

from app.models.base import Base


class EmployeeTemplate(Base):
    __tablename__ = "employee_templates"

    template_id = Column(String, primary_key=True)
    company_id = Column(String)
    name = Column(String, nullable=False)
    role = Column(String)
    description = Column(String)
    provider_id = Column(String)
    capability_id = Column(String)
    model = Column(String)
    capability_snapshot = Column(JSON, server_default="{}")
    template_scope = Column(String, server_default="company")
    status = Column(String, nullable=False, server_default="draft")
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))
