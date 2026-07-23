"""Skill entity schemas."""
from pydantic import BaseModel, Field


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    description: str | None = None
    category: str = Field(..., min_length=1, max_length=64)
    compatibility: dict | None = None


class SkillUpdate(BaseModel):
    description: str | None = None
    category: str | None = Field(default=None, min_length=1, max_length=64)
    compatibility: dict | None = None
    is_active: bool | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    version: str
    description: str | None
    category: str
    compatibility: dict | None
    is_active: bool
    checksum: str | None

    model_config = {"from_attributes": True}


class SkillListResponse(BaseModel):
    skills: list[SkillResponse]
    total: int
