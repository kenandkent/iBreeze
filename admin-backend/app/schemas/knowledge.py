from pydantic import BaseModel


class KnowledgeDocumentCreate(BaseModel):
    company_id: str
    title: str
    content: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    category: str | None = None


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None


class KnowledgeDocumentResponse(BaseModel):
    knowledge_id: str
    company_id: str
    title: str
    content: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    category: str | None = None
    status: str
    governance_confirmed: int
    created_at: str
    updated_at: str


class KnowledgeSourceResponse(BaseModel):
    source_id: str
    company_id: str
    source_type: str
    source_ref: str | None = None
    status: str
    created_at: str
