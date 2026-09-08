from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    source: str = Field(default="customer-contract")
    document_name: str = Field(default="Customer Contract - ABC.pdf")


class ReviewDecision(BaseModel):
    comment: str = ""


class PackageCreate(BaseModel):
    name: str
    description: str = ""
    proposal_ids: list[str] = Field(default_factory=list)


class QuestionRequest(BaseModel):
    question: str
    package_id: str
    context_enabled: bool = True
