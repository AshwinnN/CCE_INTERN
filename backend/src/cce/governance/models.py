"""Governance API and extraction contracts; review is an action, never a state."""

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from cce.context_packages.models.assets import Asset, Evidence, Model


class ProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProposalOperation(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"


class ProposalBatchStatus(str, Enum):
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NO_CHANGE = "NO_CHANGE"
    BUILD_BLOCKED = "BUILD_BLOCKED"
    PACKAGED = "PACKAGED"


class Actor(Model):
    actor_id: str = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)

    def require(self, role: str) -> None:
        if role not in self.roles:
            raise PermissionError(f"{role} role required")


class DomainCreate(Model):
    name: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Domain(DomainCreate):
    domain_id: UUID = Field(default_factory=uuid4)
    enabled: bool = True
    has_active_package: bool = False


class Candidate(Model):
    domain_id: UUID
    payload: Asset
    evidence: list[Evidence] = Field(min_length=1)
    operation: ProposalOperation = ProposalOperation.CREATE
    target_asset_id: UUID | None = None


class ExtractionResult(Model):
    candidates: list[Candidate] = Field(default_factory=list)


class Proposal(Model):
    proposal_id: UUID
    proposal_batch_id: UUID
    domain_id: UUID
    operation: ProposalOperation
    target_asset_id: UUID | None = None
    machine_payload: Asset
    reviewed_payload: Asset
    status: ProposalStatus = ProposalStatus.PROPOSED
    evidence: list[Evidence] = Field(default_factory=list)
    resolved_by: str | None = None
    resolved_at: str | None = None


class ReviewRequest(Model):
    proposal_id: UUID
    actor: Actor
    payload: Asset | None = None
    comment: str = ""


class ProposalFilter(Model):
    status: ProposalStatus | None = None
    domain_id: UUID | None = None
    proposal_batch_id: UUID | None = None


class BuildResult(Model):
    proposal_batch_id: UUID
    status: ProposalBatchStatus
    package_version_id: UUID | None = None
    validation_errors: list[str] = Field(default_factory=list)
