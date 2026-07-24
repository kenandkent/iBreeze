"""Compatibility rule REST contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_type: Literal["agent", "model", "skill", "client"]
    subject_id: uuid.UUID
    subject_version_range: str = Field(min_length=1, max_length=200)
    dependency_type: Literal["agent", "model", "skill", "platform", "client"]
    dependency_key: str = Field(min_length=1, max_length=200)
    dependency_version_range: str = Field(min_length=1, max_length=200)
    decision: Literal["allow", "deny"]
    reason_code: str = Field(min_length=1, max_length=100)
    priority: int


class RuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_version_range: str | None = Field(default=None, min_length=1, max_length=200)
    dependency_version_range: str | None = Field(default=None, min_length=1, max_length=200)
    decision: Literal["allow", "deny"] | None = None
    reason_code: str | None = Field(default=None, min_length=1, max_length=100)
    priority: int | None = None


class RuleResponse(RuleCreate):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    status: Literal["draft", "validated", "published"]
    created_at: datetime
    updated_at: datetime
    version: int
