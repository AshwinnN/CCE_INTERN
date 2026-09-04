"""Query runtime application service shared by gRPC and MCP adapters."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueryRequest:
    question: str
    actor_id: str | None = None
    context_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResponse:
    answer: str
    trace_id: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    context_used: bool = False


class QueryService:
    """Minimal runtime facade; future reasoning steps compose behind this boundary."""

    def query(self, request: QueryRequest) -> QueryResponse:
        return QueryResponse(
            answer="CCE query runtime is not implemented yet.",
            trace_id=request.metadata.get("trace_id"),
            context_used=False,
        )
