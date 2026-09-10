from concurrent import futures

def create_server(app):
    import grpc
    from cce.gen.cce.v1 import health_pb2_grpc,workspaces_pb2_grpc
    from cce.rpc.services.health_service import HealthService
    from cce.rpc.services.workspace_service import WorkspaceRPCService
    server=grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    health_pb2_grpc.add_HealthServiceServicer_to_server(HealthService(app),server)
    workspaces_pb2_grpc.add_WorkspaceServiceServicer_to_server(WorkspaceRPCService(app),server)
    return server

def serve(app):
    server=create_server(app)
    server.add_insecure_port(f"{app.settings.grpc_host}:{app.settings.grpc_port}")
    server.start()
    server.wait_for_termination()
