"""Source RPC mapping."""

import json


class SourceRPCService:
    def __init__(self, app):
        self.app = app

    def RegisterSource(self, request, context):
        from cce.gen.cce.v1 import common_pb2, sources_pb2

        try:
            result = self.app.source_service.register_source(
                adapter=request.adapter,
                source_id=request.source_id,
                credential_ref=request.credential_ref,
                kind=request.kind or None,
                config=json.loads(request.config_json or "{}"),
            )
            return sources_pb2.SourceResponse(
                source_id=result.source_id,
                status=result.status,
            )
        except Exception as exc:
            return sources_pb2.SourceResponse(
                source_id=request.source_id,
                status="FAILED",
                error=common_pb2.Error(
                    code="REGISTER_SOURCE_FAILED",
                    message=str(exc),
                    retryable=False,
                ),
            )

    def TestConnection(self, request, context):
        from cce.gen.cce.v1 import common_pb2, sources_pb2

        result = self.app.source_service.test_connection(request.source_id)
        payload = {
            "source_id": result.source_id,
            "status": result.status,
        }
        if result.error:
            payload["error"] = _error(common_pb2, result.error)
        return sources_pb2.SourceResponse(**payload)

    def TriggerIngestion(self, request, context):
        from cce.gen.cce.v1 import common_pb2, sources_pb2

        result = self.app.source_service.trigger_ingestion(request.source_id)
        payload = {
            "ingestion_run_id": result.ingestion_run_id,
            "status": result.status,
            "objects_processed": result.objects_processed,
            "objects_failed": result.objects_failed,
        }
        if result.error:
            payload["error"] = _error(common_pb2, result.error)
        return sources_pb2.IngestionStatus(**payload)

    def GetIngestionStatus(self, request, context):
        from cce.gen.cce.v1 import common_pb2, sources_pb2

        result = self.app.source_service.get_ingestion_status(request.ingestion_run_id)
        payload = {
            "ingestion_run_id": result.ingestion_run_id,
            "status": result.status,
            "objects_processed": result.objects_processed,
            "objects_failed": result.objects_failed,
        }
        if result.error:
            payload["error"] = _error(common_pb2, result.error)
        return sources_pb2.IngestionStatus(**payload)


def _error(common_pb2, error: dict | None):
    if not error:
        return None
    return common_pb2.Error(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
    )
