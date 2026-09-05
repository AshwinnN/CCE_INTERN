"""Query RPC mapping."""

from cce.runtime.service import QueryRequest


class QueryRPCService:
    def __init__(self, app):
        self.app = app

    def Query(self, request, context):
        from cce.gen.cce.v1 import common_pb2, query_pb2

        result = self.app.query_service.query(
            QueryRequest(
                question=request.question,
                actor_id=request.actor.actor_id,
                context_enabled=request.context_enabled,
            )
        )
        citations = [
            common_pb2.Provenance(
                source_id=item.get("source_id", ""),
                source_ref=item.get("source_ref", ""),
                version=item.get("version", ""),
            )
            for item in result.citations
        ]
        return query_pb2.QueryResponse(
            answer=result.answer,
            trace_id=result.trace_id or "",
            citations=citations,
            context_used=result.context_used,
            applied_rule=getattr(result, "applied_rule", ""),
            package_id=getattr(result, "package_id", ""),
            package_version=getattr(result, "package_version", ""),
            executed_sql=getattr(result, "executed_sql", ""),
            approver=getattr(result, "approver", ""),
            valid_until=getattr(result, "valid_until", ""),
            confidence=getattr(result, "confidence", 0.0),
        )
