from pydantic import BaseModel


class ApprovalTypeCreate(BaseModel):
    company_id: str
    name: str
    description: str | None = None
    config: dict | None = None


class ApprovalTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict | None = None


class ApprovalTypeResponse(BaseModel):
    type_id: str
    company_id: str
    name: str
    description: str | None = None
    config: dict
    version: str
    created_at: str
    updated_at: str


class BudgetPolicyResponse(BaseModel):
    id: int
    company_id: str
    version: int
    config: dict
    status: str
    created_at: str


class BudgetPolicyUpdate(BaseModel):
    config: dict


class KnowledgeRuleCreate(BaseModel):
    company_id: str
    name: str
    description: str | None = None
    category: str | None = None
    action: str = "manual_review"
    config: dict | None = None


class KnowledgeRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    action: str | None = None
    enabled: int | None = None
    config: dict | None = None


class KnowledgeRuleResponse(BaseModel):
    rule_id: str
    company_id: str
    name: str
    description: str | None = None
    category: str | None = None
    action: str
    enabled: int
    config: dict
    created_at: str
    updated_at: str
