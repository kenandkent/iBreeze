from sqlalchemy import Column, String, Integer, JSON, func

from app.models.base import Base


class ApprovalType(Base):
    __tablename__ = "approval_types"

    type_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    config = Column(JSON, server_default="{}")
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    audit_type = Column(String, nullable=False)
    actor_id = Column(String)
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(String)
    details = Column(JSON, server_default="{}")
    trace_id = Column(String)
    created_at = Column(String, server_default=func.datetime("now"))


class KnowledgeRule(Base):
    __tablename__ = "knowledge_rules"

    rule_id = Column(String, primary_key=True)
    company_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    category = Column(String)
    action = Column(String, server_default="manual_review")
    enabled = Column(Integer, server_default="1")
    config = Column(JSON, server_default="{}")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))
