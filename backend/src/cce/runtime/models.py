from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field

from cce.context_packages.models.assets import (
    Evidence,
    GovernedAsset,
    Model,
)
from cce.governance.models import Workspace


class BranchStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NO_ACTIVE_PACKAGE = "NO_ACTIVE_PACKAGE"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    DATA_SOURCE_UNRESOLVED = "DATA_SOURCE_UNRESOLVED"


class SQLErrorCode(str, Enum):
    SQL_GENERATION_FAILED = "SQL_GENERATION_FAILED"
    SQL_PARSE_FAILED = "SQL_PARSE_FAILED"
    SQL_VALIDATION_FAILED = "SQL_VALIDATION_FAILED"
    SQL_GUARD_FAILED = "SQL_GUARD_FAILED"
    SQL_EXECUTION_FAILED = "SQL_EXECUTION_FAILED"
    RETRIES_EXHAUSTED = "RETRIES_EXHAUSTED"


class QueryRequest(Model):
    question: str = Field(min_length=1, max_length=16000)
    actor_id: str | None = None
    workspace_id: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntityMention(Model):
    text: str
    entity_type: str | None = None


class QueryIntent(Model):
    intent: str
    concepts: list[str] = Field(default_factory=list)
    entities: list[EntityMention] = Field(default_factory=list)
    needs_live_data: bool = Field(description="True only when answering requires querying current transactional rows, counts, balances or record status. False for document facts, policies, procedures and reporting deadlines.")
    time_context: str | None = None
    source_hints: list[str] = Field(default_factory=list)


class WorkspaceInfo(Model):
    workspace_uuid: UUID
    workspace_id: str
    name: str


class ColumnSchema(Model):
    name: str
    data_type: str


class TableSchema(Model):
    database: str
    schema_name: str
    name: str
    columns: list[ColumnSchema]


class SourceSchema(Model):
    source_id: UUID
    source_name: str | None = None
    dialect: str = "snowflake"
    tables: list[TableSchema] = Field(default_factory=list)


class SourceSelectionRequest(Model):
    question: str
    sources: list[SourceSchema]


class SourceSelection(Model):
    source_id: UUID | None = None
    ambiguous: bool = False
    rationale: str


class VectorHit(Model):
    memory_id: str
    score: float
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEntity(Model):
    entity_id: str
    name: str
    entity_type: str = ""
    description: str = ""
    source_memories: list[str] = Field(default_factory=list)


class GraphRelationship(Model):
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    description: str = ""


class GraphContext(Model):
    status: Literal["SUCCESS", "UNAVAILABLE"] = "SUCCESS"
    entities: list[GraphEntity] = Field(default_factory=list)
    relationships: list[GraphRelationship] = Field(default_factory=list)


class ResolvedContextBundle(Model):
    package_id: UUID | None = None
    package_version_id: UUID | None = None
    version: int | None = None
    assets: list[GovernedAsset]
    vector_hits: list[VectorHit] = Field(default_factory=list)
    graph: GraphContext = Field(default_factory=GraphContext)
    warnings: list[str] = Field(default_factory=list)


class SQLGenerationRequest(Model):
    question: str
    schema_context: SourceSchema
    semantic_context: ResolvedContextBundle | None = None
    previous_sql: str | None = None
    raw_error: str | None = None
    correction_guidance: str | None = None


class SQLCandidate(Model):
    sql: str = Field(min_length=1)


class ValidationResult(Model):
    valid: bool
    error_code: SQLErrorCode | None = None
    message: str = ""
    details: list[str] = Field(default_factory=list)


class SQLErrorRequest(Model):
    sql: str
    error: str


class SQLErrorAnalysis(Model):
    error_type: str
    error_message: str
    correction_guidance: str


class SQLAttempt(Model):
    attempt_id: UUID = Field(default_factory=uuid4)
    attempt_no: int
    sql: str = ""
    parse_result: ValidationResult | None = None
    validation_result: ValidationResult | None = None
    guard_result: ValidationResult | None = None
    database_error: str | None = None
    correction_guidance: str | None = None
    status: str = "FAILED"


class SQLResult(Model):
    status: BranchStatus
    error_code: SQLErrorCode | None = None
    message: str | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    attempts: list[SQLAttempt] = Field(default_factory=list)


class Citation(Model):
    coordinates: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None
    asset_id: UUID | None = None
    asset_revision_id: UUID | None = None
    package_version_id: UUID | None = None
    evidence: Evidence | None = None
    source_id: UUID | None = None
    database: str | None = None
    schema_name: str | None = None
    tables: list[str] = Field(default_factory=list)
    sql: str | None = None
    sql_attempt_id: UUID | None = None
    memory_id: str | None = None
    source_uri: str | None = None
    retrieval_type: Literal["VECTOR", "GRAPH"] | None = None


class ContextReference(Model):
    asset_id: UUID
    asset_revision_id: UUID
    canonical_key: str


class QueryBranchResult(Model):
    status: BranchStatus
    error_code: str | None = None
    message: str | None = None
    answer: str | None = None
    sql: str | None = None
    sql_attempts: list[SQLAttempt] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    context_used: list[ContextReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnswerRequest(Model):
    feedback: list[dict[str, Any]] = Field(default_factory=list)
    question: str
    schemas: list[SourceSchema] = Field(default_factory=list)
    context: ResolvedContextBundle | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)


class AnswerResult(Model):
    answer: str


class ProofResult(Model):
    classification: Literal[
        "SAME", "DIFFERENT", "ON_IMPROVED", "OFF_IMPROVED", "NOT_COMPARABLE"
    ] = "NOT_COMPARABLE"
    explanation: str = "Both branches must succeed to compare answers."
    comparable: bool = False


class ProofRequest(Model):
    context_on: QueryBranchResult
    context_off: QueryBranchResult


class WorkflowError(Model):
    node: str
    message: str


class PackageResolution(Model):
    package_id: UUID | None = None
    package_version_id: UUID | None = None
    version: int | None = None
    status: str = "NO_ACTIVE_PACKAGE"


class AtomicQueryResponse(Model):
    trace_id: UUID
    question: str
    workspace: WorkspaceInfo
    package: PackageResolution = Field(default_factory=PackageResolution)
    context_on: QueryBranchResult
    context_off: QueryBranchResult
    proof: ProofResult = Field(default_factory=ProofResult)
    errors: list[WorkflowError] = Field(default_factory=list)


class AtomicQuestions(Model):
    questions: list[str] = Field(min_length=1, max_length=10)


class QueryResponse(Model):
    trace_id: UUID
    status: Literal['SUCCESS','PARTIAL','FAILED']
    question: str
    workspace: WorkspaceInfo
    package: dict[str, Any]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    atomic_results: list[AtomicQueryResponse] = Field(default_factory=list)
    errors: list[WorkflowError] = Field(default_factory=list)
