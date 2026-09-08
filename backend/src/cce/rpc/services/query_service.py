from cce.rpc.services.errors import rpc_errors
from google.protobuf.json_format import ParseDict

from cce.runtime.models import QueryRequest


class QueryRPCService:
    def __init__(self, app):
        self.app = app

    @rpc_errors
    def Query(self, request, context):
        from cce.gen.cce.v1 import query_pb2

        result = self.app.query_service.query(
            QueryRequest(
                question=request.question,
                actor_id=request.actor.actor_id,
                domain_id=request.domain_id or None,
                context_enabled=request.context_enabled
                if request.HasField("context_enabled")
                else True,
            )
        )
        return ParseDict(result.model_dump(mode="json"), query_pb2.QueryResponse())
