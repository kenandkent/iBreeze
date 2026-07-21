from sqlalchemy import Column, String, Integer, func

from app.models.base import Base


class Backend(Base):
    __tablename__ = "backends"

    backend_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    backend_type = Column(String, nullable=False, server_default="local_process")
    provider_id = Column(String)
    workspace_root = Column(String)
    status = Column(String, nullable=False, server_default="disabled")
    concurrency = Column(Integer, server_default="1")
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class CompanyBackendDefault(Base):
    __tablename__ = "company_backend_defaults"

    company_id = Column(String, primary_key=True)
    backend_id = Column(String, nullable=False)
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
