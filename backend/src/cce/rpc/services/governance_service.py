from cce.rpc.services.errors import rpc_errors
from google.protobuf.json_format import MessageToDict, ParseDict

from cce.governance.models import Actor, ProposalFilter, ReviewRequest


def encode(proposal):
    from cce.gen.cce.v1 import governance_pb2

    data = proposal.model_dump(mode="json")
    data["evidence_refs"] = data.pop("evidence")
    return ParseDict(data, governance_pb2.Proposal())


class GovernanceRPCService:
    def __init__(self, app):
        self.app = app

    @rpc_errors
    def ListProposals(self, request, context):
        from cce.gen.cce.v1 import governance_pb2

        filters = ProposalFilter(
            status=request.status or None,
            domain_id=request.domain_id or None,
            proposal_batch_id=request.proposal_batch_id or None,
        )
        return governance_pb2.ListProposalsResponse(
            proposals=[
                encode(p) for p in self.app.governance_service.list_proposals(filters)
            ]
        )

    @rpc_errors
    def GetProposal(self, request, context):
        return encode(self.app.governance_service.get_proposal(request.proposal_id))

    def _request(self, request, comment="", payload=None):
        return ReviewRequest(
            proposal_id=request.proposal_id,
            actor=Actor(
                actor_id=request.actor.actor_id, roles=list(request.actor.roles)
            ),
            comment=comment,
            payload=payload,
        )

    @rpc_errors
    def EditProposal(self, request, context):
        return encode(
            self.app.governance_service.edit_proposal(
                self._request(request, request.comment, MessageToDict(request.payload))
            )
        )

    @rpc_errors
    def ApproveProposal(self, request, context):
        return encode(
            self.app.governance_service.approve_proposal(
                self._request(request, request.comment)
            )
        )

    @rpc_errors
    def RejectProposal(self, request, context):
        return encode(
            self.app.governance_service.reject_proposal(
                self._request(request, request.reason)
            )
        )
