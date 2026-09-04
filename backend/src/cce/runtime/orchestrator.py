"""Governed Context ON/OFF query orchestration placeholder."""

from cce.runtime.service import QueryRequest, QueryResponse


class RuntimeOrchestrator:
    def run(self, request: QueryRequest) -> QueryResponse:
        return QueryResponse(answer="CCE query runtime is not implemented yet.")
