from cce.governance.models import ProposalFilter, ReviewRequest


class GovernanceService:
    def __init__(self, repository):
        self.repository = repository

    def list_proposals(self, filters: ProposalFilter | None = None):
        return self.repository.list(filters or ProposalFilter())

    def get_proposal(self, proposal_id):
        return self.repository.get(proposal_id)

    def edit_proposal(self, request: ReviewRequest):
        return self.repository.review(request, "EDIT")

    def approve_proposal(self, request: ReviewRequest):
        return self.repository.review(request, "APPROVE")

    def reject_proposal(self, request: ReviewRequest):
        return self.repository.review(request, "REJECT")
