"""Health RPC handler."""


class HealthService:
    def __init__(self, app):
        self.app = app

    def Check(self, request, context):
        from cce.gen.cce.v1 import health_pb2

        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)
