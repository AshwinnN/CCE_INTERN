"""Health RPC handler."""


class HealthService:
    def __init__(self, app):
        self.app = app

    def Check(self, request, context):
        from cce.gen.cce.v1 import health_pb2

        status = (
            health_pb2.HealthCheckResponse.SERVING
            if getattr(self.app, "ready", False)
            else health_pb2.HealthCheckResponse.NOT_SERVING
        )
        return health_pb2.HealthCheckResponse(status=status)
