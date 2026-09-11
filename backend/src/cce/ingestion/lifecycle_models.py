"""Source-level workflow state values; SDK dictionaries remain inside grounding boundary."""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from cce.context_packages.models.assets import GovernedAsset, Model
from cce.governance.models import Domain
from cce.runtime.models import DomainCandidate, VectorHit


class IngestionRunStatus(str, Enum):
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ItemChangeType(str, Enum):
    NEW = "NEW"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    MISSING = "MISSING"


class ItemProcessingStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DOMAIN_UNRESOLVED = "DOMAIN_UNRESOLVED"


class SourceItem(Model):
    source_item_id: UUID
    source_id: UUID
    source_native_id: str | None = None
    canonical_uri: str
    content_hash: str = ""
    change_type: ItemChangeType
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRun(Model):
    ingestion_run_id: UUID
    source_id: UUID
    status: IngestionRunStatus
    objects_processed: int = 0
    objects_failed: int = 0
    error: str | None = None


class ItemResult(Model):
    item: SourceItem
    status: ItemProcessingStatus
    domains: list[DomainCandidate] = Field(default_factory=list)
    error: str | None = None


class DomainDetectionRequest(Model):
    source_item: SourceItem
    content: str
    domains: list[Domain]


class ExtractionRequest(Model):
    source_item: SourceItem
    domain: Domain
    evidence: list[VectorHit]
    active_assets: list[GovernedAsset] = Field(default_factory=list)


class SourceRunRequest(Model):
    ingestion_run_id: UUID
    source_id: UUID
    claim_token: UUID


class InventoryResult(Model):
    items: list[SourceItem]


class IndexCell(Model):
    row: int
    col: int
    text: str

class IndexBlock(Model):
    id: str
    type: str = 'text'
    text: str = ''
    cells: list[IndexCell] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class GroundingPayload(Model):
    document_id: str
    source_id: UUID
    source_ref: str
    object_id: str
    revision: str
    trace_id: UUID
    blocks: list[IndexBlock]
    metadata: dict[str, Any] = Field(default_factory=dict)

class GroundedItem(Model):
    content: str
    payload: GroundingPayload


class ItemWork(Model):
    request: SourceRunRequest
    item: SourceItem
