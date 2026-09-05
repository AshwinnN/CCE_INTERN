"""Governance RPC mapping."""


class GovernanceRPCService:
    def __init__(self, app):
        self.app = app

    def ListProposals(self, request, context):
        from cce.gen.cce.v1 import common_pb2, governance_pb2

        proposals = [
            governance_pb2.Proposal(
                proposal_id=item.get("proposal_id", ""),
                status=item.get("status", ""),
                asset_type=item.get("asset_type", ""),
                payload=item.get("payload", ""),
                evidence=[
                    common_pb2.Provenance(
                        source_id=evidence.get("source_id", ""),
                        source_ref=evidence.get("source_ref", ""),
                        version=evidence.get("version", ""),
                    )
                    for evidence in item.get("evidence", [])
                ],
                proposed_at=item.get("proposed_at", ""),
                approved_at=item.get("approved_at", ""),
                approver=item.get("approver", ""),
                valid_until=item.get("valid_until", ""),
            )
            for item in self.app.governance_service.list_proposals()
        ]
        return governance_pb2.ListProposalsResponse(proposals=proposals)

    def GetProposal(self, request, context):
        from cce.gen.cce.v1 import common_pb2, governance_pb2

        proposal = self.app.governance_service.get_proposal(request.proposal_id)
        return governance_pb2.Proposal(
            proposal_id=proposal["proposal_id"],
            status=proposal["status"],
            asset_type=proposal.get("asset_type", ""),
            payload=proposal.get("payload", ""),
            evidence=[
                common_pb2.Provenance(
                    source_id=evidence.get("source_id", ""),
                    source_ref=evidence.get("source_ref", ""),
                    version=evidence.get("version", ""),
                )
                for evidence in proposal.get("evidence", [])
            ],
            proposed_at=proposal.get("proposed_at", ""),
            approved_at=proposal.get("approved_at", ""),
            approver=proposal.get("approver", ""),
            valid_until=proposal.get("valid_until", ""),
        )

    def ApproveProposal(self, request, context):
        from cce.gen.cce.v1 import governance_pb2

        proposal = self.app.governance_service.approve_proposal(
            request.proposal_id, request.comment
        )
        return governance_pb2.Proposal(
            proposal_id=proposal["proposal_id"],
            status=proposal["status"],
            asset_type=proposal.get("asset_type", ""),
            payload=proposal.get("payload", ""),
            proposed_at=proposal.get("proposed_at", ""),
            approved_at=proposal.get("approved_at", ""),
            approver=proposal.get("approver", ""),
            valid_until=proposal.get("valid_until", ""),
        )

    def RejectProposal(self, request, context):
        from cce.gen.cce.v1 import governance_pb2

        proposal = self.app.governance_service.reject_proposal(
            request.proposal_id, request.reason
        )
        return governance_pb2.Proposal(
            proposal_id=proposal["proposal_id"],
            status=proposal["status"],
            asset_type=proposal.get("asset_type", ""),
            payload=proposal.get("payload", ""),
            proposed_at=proposal.get("proposed_at", ""),
            approved_at=proposal.get("approved_at", ""),
            approver=proposal.get("approver", ""),
            valid_until=proposal.get("valid_until", ""),
        )
