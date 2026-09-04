"""Steward-facing governance use cases."""

from cce.core.errors import NotImplementedCCEError


class GovernanceService:
    def list_proposals(self):
        raise NotImplementedCCEError("governance service is not implemented yet")
