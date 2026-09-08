from cce.rpc.services.errors import rpc_errors
from google.protobuf.json_format import MessageToDict, ParseDict

from cce.governance.models import Actor, DomainCreate


class DomainRPCService:
    def __init__(self, app):
        self.app = app

    @rpc_errors
    def CreateDomain(self, request, context):
        from cce.gen.cce.v1 import domains_pb2

        domain = self.app.domain_repository.create(
            DomainCreate(
                name=request.name,
                description=request.description,
                tags=list(request.tags),
                metadata=MessageToDict(request.metadata),
            ),
            Actor(actor_id=request.actor.actor_id, roles=list(request.actor.roles)),
        )
        return ParseDict(domain.model_dump(mode="json"), domains_pb2.Domain())

    @rpc_errors
    def ListDomains(self, request, context):
        from cce.gen.cce.v1 import domains_pb2

        return ParseDict(
            {
                "domains": [
                    d.model_dump(mode="json") for d in self.app.domain_repository.list()
                ]
            },
            domains_pb2.ListDomainsResponse(),
        )
