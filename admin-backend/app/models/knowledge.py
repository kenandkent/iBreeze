from sqlalchemy import Column, String, Integer, JSON, func

from app.models.base import Base


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    knowledge_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    content = Column(String)
    source_type = Column(String)
    source_id = Column(String)
    category = Column(String)
    status = Column(String, server_default="active")
    governance_confirmed = Column(Integer, server_default="0")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    source_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    source_ref = Column(String)
    status = Column(String, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))


class KnowledgePolicy(Base):
    __tablename__ = "knowledge_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    config = Column(JSON, nullable=False, server_default="{}")
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))


class SecurityPolicy(Base):
    __tablename__ = "security_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    config = Column(JSON, nullable=False, server_default="{}")
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))


class WorkspacePolicy(Base):
    __tablename__ = "workspace_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    config = Column(JSON, nullable=False, server_default="{}")
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))


class NotificationPolicy(Base):
    __tablename__ = "notification_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    config = Column(JSON, nullable=False, server_default="{}")
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))


class BudgetPolicy(Base):
    __tablename__ = "budget_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False, server_default="1")
    config = Column(JSON, nullable=False, server_default="{}")
    status = Column(String, nullable=False, server_default="active")
    created_at = Column(String, server_default=func.datetime("now"))
