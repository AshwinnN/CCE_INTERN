from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MemoryStoreRequest(BaseModel):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    content: Optional[Any] = None


class MemoryStoreBatchRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str
    limit: Optional[int] = None
    filters: Dict[str, Any] = Field(default_factory=dict)
