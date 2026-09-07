"""gRPC server assembly."""

from concurrent import futures
from typing import Any


def create_server(app: Any):
    import grpc

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    from cce.gen.cce.v1 import (
        governance_pb2_grpc,
        health_pb2_grpc,
        packages_pb2_grpc,
        query_pb2_grpc,
        retrieval_pb2_grpc,
        sources_pb2_grpc,
    )
    from cce.rpc.services.governance_service import GovernanceRPCService
    from cce.rpc.services.health_service import HealthService
    from cce.rpc.services.package_service import PackageRPCService
    from cce.rpc.services.query_service import QueryRPCService
    from cce.rpc.services.retrieval_service import RetrievalRPCService
    from cce.rpc.services.source_service import SourceRPCService

    health_pb2_grpc.add_HealthServiceServicer_to_server(HealthService(app), server)
    sources_pb2_grpc.add_SourceServiceServicer_to_server(
        SourceRPCService(app), server
    )
    query_pb2_grpc.add_QueryServiceServicer_to_server(QueryRPCService(app), server)
    retrieval_pb2_grpc.add_RetrievalServiceServicer_to_server(
        RetrievalRPCService(app), server
    )
    governance_pb2_grpc.add_GovernanceServiceServicer_to_server(
        GovernanceRPCService(app), server
    )
    packages_pb2_grpc.add_PackageServiceServicer_to_server(
        PackageRPCService(app), server
    )
    return server


def serve(app: Any) -> None:
    server = create_server(app)
    address = "%s:%s" % (app.settings.grpc_host, app.settings.grpc_port)
    server.add_insecure_port(address)
    server.start()
    server.wait_for_termination()
