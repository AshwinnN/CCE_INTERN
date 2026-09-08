"""Single query entry point for HTTP, gRPC, and MCP."""

from cce.runtime.models import QueryRequest, QueryResponse


class QueryService:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    def query(self, request: QueryRequest) -> QueryResponse:
        return self.orchestrator.run(request)
