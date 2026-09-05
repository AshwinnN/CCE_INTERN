"""Steward-facing governance use cases."""


class GovernanceService:
    def list_proposals(self):
        return []

    def get_proposal(self, proposal_id: str):
        return {"proposal_id": proposal_id, "status": "NOT_FOUND"}

    def approve_proposal(self, proposal_id: str, comment: str | None = None):
        return {"proposal_id": proposal_id, "status": "NOT_FOUND"}

    def reject_proposal(self, proposal_id: str, reason: str | None = None):
        return {"proposal_id": proposal_id, "status": "NOT_FOUND"}
