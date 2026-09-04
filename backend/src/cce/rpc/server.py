"""gRPC server assembly.

Generated protobuf modules are loaded only if `scripts/generate_proto.py`
has been run. The module remains importable without generated code so local
tests can validate package wiring without checking in generated artifacts.
"""

from concurrent import futures
from typing import Any


def create_server(app: Any):
    import grpc

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    try:
        from cce.gen.cce.v1 import health_pb2_grpc
        from cce.rpc.services.health_service import HealthService
    except ImportError:
        return server

    health_pb2_grpc.add_HealthServiceServicer_to_server(HealthService(app), server)
    return server


def serve(app: Any) -> None:
    server = create_server(app)
    address = "%s:%s" % (app.settings.grpc_host, app.settings.grpc_port)
    server.add_insecure_port(address)
    server.start()
    server.wait_for_termination()
