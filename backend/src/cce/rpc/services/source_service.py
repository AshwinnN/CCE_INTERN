"""Source RPC mapping."""


class SourceRPCService:
    def __init__(self, app):
        self.app = app

    def RegisterSource(self, request, context):
        from cce.gen.cce.v1 import sources_pb2

        saved_id = self.app.source_repository.save_source(
            adapter=request.adapter,
            source_id=request.source_id,
            credential_ref=request.credential_ref,
        )
        return sources_pb2.SourceResponse(source_id=saved_id, status="REGISTERED")

    def TestConnection(self, request, context):
        from cce.gen.cce.v1 import common_pb2, sources_pb2

        return sources_pb2.SourceResponse(
            source_id=request.source_id,
            status="NOT_CONFIGURED",
            error=common_pb2.Error(
                code="NOT_IMPLEMENTED",
                message="Connection testing is not implemented in the server foundation.",
                retryable=False,
            ),
        )

    def TriggerIngestion(self, request, context):
        from cce.gen.cce.v1 import common_pb2, sources_pb2

        return sources_pb2.IngestionStatus(
            ingestion_run_id="",
            status="NOT_STARTED",
            error=common_pb2.Error(
                code="NOT_IMPLEMENTED",
                message="Ingestion triggering is not implemented in the server foundation.",
                retryable=False,
            ),
        )

    def GetIngestionStatus(self, request, context):
        from cce.gen.cce.v1 import sources_pb2

        return sources_pb2.IngestionStatus(
            ingestion_run_id=request.ingestion_run_id,
            status="UNKNOWN",
        )
