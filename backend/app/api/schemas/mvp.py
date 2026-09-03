from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class PlaceholderRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


class QueryRequest(BaseModel):
    question: str
    tenant_id: Optional[str] = None
    context_enabled: bool = True


class ApprovalRequest(BaseModel):
    approved_by: str
    comment: Optional[str] = None
