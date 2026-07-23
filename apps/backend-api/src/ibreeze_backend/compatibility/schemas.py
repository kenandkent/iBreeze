"""Compatibility rule schemas."""
from pydantic import BaseModel, Field


class CompatibilityRuleCreate(BaseModel):
    subject_type: str = Field(..., min_length=1, max_length=64)
    subject_version_range: dict | None = None
    dependency_type: str = Field(..., min_length=1, max_length=64)
    dependency_version_range: dict | None = None
    result: str = Field(..., pattern="^(allow|deny)$")
    reason_code: str | None = Field(default=None, max_length=64)
    priority: int = 0


class CompatibilityRuleUpdate(BaseModel):
    subject_type: str | None = Field(default=None, min_length=1, max_length=64)
    subject_version_range: dict | None = None
    dependency_type: str | None = Field(default=None, min_length=1, max_length=64)
    dependency_version_range: dict | None = None
    result: str | None = Field(default=None, pattern="^(allow|deny)$")
    reason_code: str | None = Field(default=None, max_length=64)
    priority: int | None = None


class CompatibilityRuleResponse(BaseModel):
    id: str
    subject_type: str
    subject_version_range: dict | None
    dependency_type: str
    dependency_version_range: dict | None
    result: str
    reason_code: str | None
    priority: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CompatibilityRuleListResponse(BaseModel):
    rules: list[CompatibilityRuleResponse]
    total: int


class EvaluateRequest(BaseModel):
    subject_type: str = Field(..., min_length=1, max_length=64)
    subject_version: str | None = None
    dependency_type: str = Field(..., min_length=1, max_length=64)
    dependency_version: str | None = None


class EvaluateResponse(BaseModel):
    result: str
    reason_code: str | None = None
    matched_rule_id: str | None = None
