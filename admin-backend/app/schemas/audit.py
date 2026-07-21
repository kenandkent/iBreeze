from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    log_id: str
    company_id: str
    audit_type: str
    actor_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict
    trace_id: str | None = None
    created_at: str


class InterventionResponse(BaseModel):
    log_id: str
    company_id: str
    actor_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict
    created_at: str
