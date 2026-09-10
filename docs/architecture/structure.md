# CCE Tool — Target Repository Structure

CCE (CoStrategix Context Engine) is a **governed context server**. It owns source registration, ingestion orchestration, governance, context packages, query-time reasoning, guarded structured-data access, traceability, and MCP exposure.

CCE does **not** own the target long-term vector storage, graph storage, graph extraction, or retrieval infrastructure. Those capabilities are consumed through the external **AgenticPlane Python SDK**. For MVP synthetic proof, `cce.integrations.agentic_plane.LocalIndexClient` provides a pgvector-backed local implementation behind the same boundary; it is not a second domain/runtime architecture.

## Architecture rules

- Organize code by CCE capability/module, not by generic `common` or framework names.
- Use **gRPC + Protobuf** as the primary server contract; the only JSON/HTTP surface is the thin adapter described in `docs/decisions/ADR-004-json-adapter.md`.
- Keep the CCE core domain-blind; domain knowledge lives in governed context packages.
- Keep deterministic logic deterministic. Use agents only where reasoning is required.
- Skills are versioned agent assets (`SKILL.md`, scripts, references), not generic prompts.
- Use PostgreSQL database **`cce_control`** as the CCE control/governance store.
- Treat AgenticPlane as an external platform accessed only through an integration adapter.
- Keep engineering observability separate from governance/audit traceability.
- MCP is a thin transport adapter over the same CCE query runtime.
- Use `pyproject.toml`; do not maintain `requirements.txt` as the primary dependency file.

---

## How to explore and change safely

Start with `docs/IMPLEMENTATION_STATUS.md`, `docs/component-map.yaml`, this
document, and then the nearest module `AGENTS.md`. Follow the exact entry point
for the requested change and read outward through imports/calls only as needed.
Code remains the source of truth when a doc and implementation disagree.

For connector or parser work, avoid governance/runtime/MCP unless the public
contract crosses that boundary. For governance, package, runtime or trace work,
label new code as implementing a known gap rather than treating placeholder
services as precedent. For backend-only work, do not inspect `frontend/`; it has
no application implementation today.

Treat adapter registry `status="READY"` as metadata, not proof of an executable
connector. Verify the factory/provider implementation before relying on an
adapter.

| Change type | Start here | Avoid unless the boundary changes |
|---|---|---|
| Structured connector | `connectors/structured/<adapter>/`, `connectors/factory.py` | governance/runtime/MCP |
| Parser/file type | `ingestion/parsers/`, `ParserFactory` | connector registry, runtime |
| Structured metadata | ingestion persistence node, `persistence/ports.py`, Postgres repo/migration | frontend/MCP |
| Proposal approval | `governance/` and governance migration/repository | provider/parser internals |
| Package versioning | `context_packages/` and context migration/repository | source discovery |
| Query/proof | `runtime/` plus package/governance/trace contracts | parser internals |
| Public API | proto, transport mapping, backing service | duplicated transport business logic |

High-impact files to change deliberately: `backend/proto/cce/v1/*.proto`,
`backend/src/cce/bootstrap.py`, connector/change-event contracts, ingestion
models/orchestrator, persistence ports/migrations/repositories, and the
Snowflake connector read-only boundary.

---

## Target repository layout

```text
CCE-Tool/
│
├── README.md                                  # Product overview, local setup, architecture links and run commands.
├── .gitignore                                 # Ignores secrets, caches, generated files and local runtime artifacts.
├── docker-compose.yaml                        # Local CCE stack: backend + cce_control PostgreSQL only.
│
├── backend/
│   ├── pyproject.toml                         # Python package metadata, runtime dependencies and dev/test tooling.
│   ├── .env.example                           # Documented backend configuration with safe placeholder values.
│   │
│   ├── proto/
│   │   └── cce/
│   │       └── v1/
│   │           ├── common.proto               # Shared IDs, pagination, actor, provenance and error message types.
│   │           ├── health.proto               # Liveness/readiness RPC contract.
│   │           └── workspaces.proto           # Single WorkspaceService action-dispatch RPC: Workspace CRUD, source-types/discover/sources, proposals, package/versions, query, feedback and retrieve.
│   │
│   ├── src/
│   │   └── cce/
│   │       ├── __init__.py                    # CCE Python package marker and package version export.
│   │       ├── main.py                        # Server entry point; loads settings and starts the gRPC server.
│   │       ├── bootstrap.py                   # Composition root; wires repositories, integrations, services and agents.
│   │       │
│   │       ├── config/
│   │       │   ├── __init__.py                # Configuration package exports.
│   │       │   └── settings.py                # Typed environment configuration for CCE and external dependencies.
│   │       │
│   │       ├── rpc/
│   │       │   ├── __init__.py                # gRPC transport package exports.
│   │       │   ├── server.py                  # Creates gRPC server, interceptors and registers service handlers.
│   │       │   │
│   │       │   ├── interceptors/
│   │       │   │   ├── __init__.py            # Interceptor exports.
│   │       │   │   ├── authentication.py      # Resolves caller identity before service execution.
│   │       │   │   ├── authorization.py       # Enforces Admin, Steward and Query Consumer permissions.
│   │       │   │   ├── correlation.py         # Creates/propagates request and trace identifiers.
│   │       │   │   └── logging.py             # Emits engineering request diagnostics without governance semantics.
│   │       │   │
│   │       │   └── services/
│   │       │       ├── __init__.py            # gRPC service handler exports.
│   │       │       ├── health_service.py      # Implements liveness/readiness checks.
│   │       │       ├── query_service.py       # Maps Query RPC requests to runtime QueryService.
│   │       │       ├── source_service.py      # Maps Admin source/ingestion RPCs to source and ingestion services.
│   │       │       ├── governance_service.py  # Maps Steward lifecycle RPCs to governance services.
│   │       │       └── package_service.py     # Maps package RPCs to context package services.
│   │       │
│   │       ├── gen/
│   │       │   └── cce/v1/                    # Generated protobuf/gRPC Python code; never edit manually.
│   │       │
│   │       ├── core/
│   │       │   ├── __init__.py                # Domain-neutral core exports.
│   │       │   ├── enums.py                   # Shared lifecycle, source, actor and asset enums.
│   │       │   ├── errors.py                  # Stable CCE domain exceptions independent of transport/frameworks.
│   │       │   ├── types.py                   # Shared strongly typed aliases/value objects.
│   │       │   └── models/
│   │       │       ├── __init__.py            # Core model exports.
│   │       │       ├── actor.py               # Caller identity and role information.
│   │       │       ├── source.py              # Domain-neutral source identity/configuration models.
│   │       │       ├── provenance.py          # Source/version/location lineage attached to context assets.
│   │       │       └── context_asset.py       # Base model for proposed/approved governed context assets.
│   │       │
│   │       ├── connectors/
│   │       │   ├── __init__.py                # Connector package exports.
│   │       │   ├── registry.py                # Registry of supported connector implementations.
│   │       │   ├── factory.py                 # Creates connectors from persisted source configuration.
│   │       │   │
│   │       │   ├── base/
│   │       │   │   ├── __init__.py            # Base connector exports.
│   │       │   │   ├── connector.py           # Common connector lifecycle interface.
│   │       │   │   ├── structured.py          # Interface for schema discovery, samples and read-only SQL execution.
│   │       │   │   ├── unstructured.py        # Interface for listing, reading and identifying changed documents.
│   │       │   │   ├── models.py              # Canonical connector request/result models.
│   │       │   │   └── exceptions.py          # Connector-specific normalized error types.
│   │       │   │
│   │       │   ├── structured/
│   │       │   │   └── snowflake/
│   │       │   │       ├── __init__.py        # Snowflake connector exports.
│   │       │   │       ├── config.py          # Validated Snowflake connection options and read-only settings.
│   │       │   │       └── connector.py       # Snowflake discovery, sampling and guarded query implementation.
│   │       │   │
│   │       │   └── unstructured/
│   │       │       └── azure_blob/
│   │       │           ├── __init__.py        # Azure Blob connector exports.
│   │       │           ├── config.py           # Validated Azure Blob source configuration.
│   │       │           └── connector.py        # Lists, reads and fingerprints documents from Azure Blob.
│   │       │
│   │       ├── ingestion/
│   │       │   ├── __init__.py                # Ingestion package exports.
│   │       │   ├── service.py                 # Top-level ingestion use case invoked by Admin/source triggers.
│   │       │   ├── models.py                  # Canonical document, schema snapshot and ingestion result models.
│   │       │   ├── orchestrator.py             # Coordinates source fetch, normalization, DLP, persistence and indexing.
│   │       │   ├── checkpoint.py               # Persists/resolves ingestion progress and last-seen source versions.
│   │       │   │
│   │       │   ├── structured/
│   │       │   │   ├── __init__.py            # Structured ingestion exports.
│   │       │   │   └── ingest.py              # Discovers schemas/samples and writes structured metadata snapshots.
│   │       │   │
│   │       │   ├── unstructured/
│   │       │   │   ├── __init__.py            # Unstructured ingestion exports.
│   │       │   │   └── ingest.py              # Fetches changed documents, normalizes them and sends them for indexing.
│   │       │   │
│   │       │   ├── change_detection/
│   │       │   │   ├── __init__.py            # Change detection exports.
│   │       │   │   ├── structured.py          # Detects schema/table metadata changes between snapshots.
│   │       │   │   └── documents.py           # Detects new/changed/deleted source documents.
│   │       │   │
│   │       │   ├── parsers/
│   │       │   │   ├── __init__.py            # Parser exports.
│   │       │   │   ├── base.py                # Parser interface returning the canonical document model.
│   │       │   │   ├── factory.py             # Chooses parser by MIME type/file extension.
│   │       │   │   ├── docling.py             # PDF/DOCX/PPTX parsing through Docling.
│   │       │   │   ├── excel.py               # XLS/XLSX normalization through openpyxl.
│   │       │   │   ├── csv.py                 # CSV normalization preserving tabular metadata.
│   │       │   │   ├── image.py               # Image extraction/OCR adapter when document text is unavailable.
│   │       │   │   └── text.py                # Plain-text/Markdown parser.
│   │       │   │
│   │       │   └── normalizers/
│   │       │       ├── __init__.py             # Normalizer exports.
│   │       │       ├── document.py             # Converts parser output into the canonical unstructured schema.
│   │       │       └── structured.py           # Converts warehouse metadata into canonical structured metadata.
│   │       │
│   │       ├── governance/
│   │       │   ├── __init__.py                 # Governance package exports.
│   │       │   ├── models.py                   # Proposal, review, approval and rejection domain models.
│   │       │   ├── state_machine.py            # Defines valid Propose → Review → Approve/Reject/Evolve transitions.
│   │       │   ├── policy.py                   # Enforces approved-only serving and governance invariants.
│   │       │   ├── service.py                  # Steward-facing proposal review/approval/rejection use cases.
│   │       │   └── evolution.py                # Creates new proposed revisions from approved asset feedback/changes.
│   │       │
│   │       ├── context_packages/
│   │       │   ├── __init__.py                 # Context package exports.
│   │       │   ├── service.py                  # Creates, retrieves and manages the one governed context package per Workspace.
│   │       │   ├── builder.py                  # Builds package versions from approved context assets only.
│   │       │   ├── versioning.py               # Controls immutable package versions and version bumps.
│   │       │   ├── inheritance.py              # Unused override-layering placeholder; four-tier Global/Workspace/Region/Account inheritance is explicitly out of scope for this MVP.
│   │       │   ├── validator.py                # Validates package consistency before activation.
│   │       │   └── models/
│   │       │       ├── __init__.py             # Package model exports.
│   │       │       ├── package.py              # Workspace context package identity, scope, status and version metadata.
│   │       │       ├── glossary.py             # Canonical term, definition, synonyms and citations.
│   │       │       ├── semantic_mapping.py     # Business concept → physical structured-data mapping.
│   │       │       ├── policy_rule.py          # Governed business rule, conditions, values and validity window.
│   │       │       ├── verified_sql.py         # Human-approved SQL/template plus binding metadata.
│   │       │       └── ambiguity.py            # Approved conflicting meanings and pinned interpretations.
│   │       │
│   │       ├── runtime/
│   │       │   ├── __init__.py                 # Query runtime exports.
│   │       │   ├── service.py                  # Single application entry point used by gRPC and MCP query calls.
│   │       │   ├── orchestrator.py             # Coordinates the complete governed Context ON/OFF execution flow.
│   │       │   ├── state.py                    # Typed runtime state shared across reasoning/execution steps.
│   │       │   ├── intent.py                   # Determines question intent and required runtime capabilities.
│   │       │   ├── retrieval.py                # Starts retrieval through AgenticPlane and normalizes returned evidence.
│   │       │   ├── entity_resolution.py        # Resolves question/retrieval entities to canonical structured entities.
│   │       │   ├── ambiguity.py                # Detects unresolved terms/entities requiring pinned interpretation.
│   │       │   ├── package_resolver.py         # Resolves active package hierarchy and applicable package versions.
│   │       │   ├── context_assembler.py        # Assembles approved glossary, rules, mappings and evidence for Context ON.
│   │       │   ├── rule_resolver.py            # Selects and validates the business rules applicable to the question.
│   │       │   ├── semantic_resolver.py        # Resolves business concepts to structured data objects/columns.
│   │       │   ├── live_data.py                # Determines whether fresh structured data is required.
│   │       │   ├── sql_generator.py            # Generates candidate SQL only when verified SQL is unavailable.
│   │       │   ├── sql_guard.py                # Enforces SELECT-only, timeout, row-limit and allowed-object constraints.
│   │       │   ├── query_executor.py           # Executes guarded SQL through the selected structured connector.
│   │       │   ├── rule_engine.py              # Applies approved rules/overrides to live query results.
│   │       │   ├── answer_builder.py           # Produces governed answer, explanation, citations and confidence metadata.
│   │       │   └── proof_engine.py             # Runs/compares Context OFF vs Context ON and calculates proof output.
│   │       │
│   │       ├── agents/
│   │       │   ├── __init__.py                 # Agent package exports.
│   │       │   ├── base.py                     # Common agent execution contract and typed result handling.
│   │       │   ├── query_agent.py              # Agentic reasoning used by query runtime where deterministic logic is insufficient.
│   │       │   └── proposal_agent.py           # Proposes glossary/rule/mapping candidates; never directly approves them.
│   │       │
│   │       ├── skills/
│   │       │   ├── __init__.py                 # Skill runtime exports.
│   │       │   ├── models.py                   # Skill metadata, dependencies, tool permissions and version models.
│   │       │   ├── loader.py                   # Loads and validates SKILL.md plus referenced assets.
│   │       │   └── registry.py                 # Resolves available skills and their declared dependencies.
│   │       │
│   │       ├── integrations/
│   │       │   ├── __init__.py                 # External platform integration exports.
│   │       │   └── agentic_plane/
│   │       │       ├── __init__.py             # AgenticPlane integration exports.
│   │       │       ├── config.py               # Endpoint/project/auth configuration for the external SDK.
│   │       │       ├── client.py               # Thin CCE wrapper over the supplied AgenticPlane Python SDK.
│   │       │       ├── mapper.py               # Maps CCE models/filters to and from AgenticPlane SDK models.
│   │       │       └── models.py               # CCE-side typed representation of AgenticPlane retrieval/index results.
│   │       │
│   │       ├── persistence/
│   │       │   ├── __init__.py                 # Persistence package exports.
│   │       │   ├── ports.py                    # Repository interfaces consumed by CCE application modules.
│   │       │   └── postgres/
│   │       │       ├── __init__.py             # PostgreSQL persistence exports.
│   │       │       ├── database.py             # Connection pool/session management for database `cce_control`.
│   │       │       ├── source_repository.py    # Persists source registry, versions and ingestion state.
│   │       │       ├── metadata_repository.py  # Persists structured schema/table/column/sample snapshots.
│   │       │       ├── governance_repository.py# Persists proposals, reviews, approvals and lifecycle history.
│   │       │       ├── package_repository.py   # Persists packages, versions and governed package assets.
│   │       │       ├── runtime_repository.py   # Persists query/execution metadata needed for tracking/evaluation.
│   │       │       └── audit_repository.py     # Append-only persistence for governance/traceability events.
│   │       │
│   │       ├── security/
│   │       │   ├── __init__.py                 # Security package exports.
│   │       │   ├── authentication.py           # Validates caller/service identity.
│   │       │   ├── authorization.py            # Role and resource-level access policy.
│   │       │   ├── credentials.py              # Resolves encrypted credential references; never exposes raw secrets.
│   │       │   ├── entitlements.py             # Captures/enforces source and retrieval access entitlements.
│   │       │   └── dlp.py                      # DLP/PII classification and redaction before context becomes eligible.
│   │       │
│   │       ├── traceability/
│   │       │   ├── __init__.py                 # Governance traceability exports.
│   │       │   ├── models.py                   # Audit event, answer trace and lineage data models.
│   │       │   ├── events.py                   # Stable governance event names and payload contracts.
│   │       │   ├── service.py                  # Records governance changes and query context usage.
│   │       │   └── answer_trace.py             # Builds trace ID, source/rule/package/approver metadata returned with answers.
│   │       │
│   │       ├── observability/
│   │       │   ├── __init__.py                 # Engineering observability exports.
│   │       │   ├── config.py                   # Debug/log/trace toggles and exporter configuration.
│   │       │   ├── logging.py                  # Application diagnostic logging.
│   │       │   ├── tracing.py                  # Engineering distributed tracing/span helpers.
│   │       │   └── metrics.py                  # Latency, error, ingestion and execution metrics.
│   │       │
│   │       └── mcp/
│   │           ├── __init__.py                 # MCP adapter exports.
│   │           ├── server.py                   # Creates the MCP server and registers CCE tools.
│   │           └── tools/
│   │               ├── __init__.py             # MCP tool exports.
│   │               └── query.py                # Thin MCP tool calling the same runtime.service QueryService.
│   │
│   ├── skills/
│   │   ├── README.md                           # Skill authoring rules, metadata schema and testing conventions.
│   │   │
│   │   ├── context_resolution/
│   │   │   ├── SKILL.md                        # Procedure/constraints for assembling governed business context.
│   │   │   ├── scripts/
│   │   │   │   └── validate_context.py         # Deterministic validation helper allowed by this skill.
│   │   │   └── references/
│   │   │       └── context_rules.md            # Curated reference material loaded only when the skill requires it.
│   │   │
│   │   ├── entity_resolution/
│   │   │   ├── SKILL.md                        # Procedure for resolving business entities without guessing identifiers.
│   │   │   ├── scripts/
│   │   │   │   └── rank_candidates.py          # Deterministic candidate scoring/ranking helper.
│   │   │   └── references/
│   │   │       └── resolution_rules.md         # Resolution constraints and ambiguity examples.
│   │   │
│   │   ├── semantic_mapping/
│   │   │   ├── SKILL.md                        # Procedure for mapping business concepts to structured metadata.
│   │   │   └── references/
│   │   │       └── mapping_guidelines.md       # Mapping quality rules and examples.
│   │   │
│   │   ├── policy_interpretation/
│   │   │   ├── SKILL.md                        # Procedure for extracting/interpreting candidate business rules.
│   │   │   └── references/
│   │   │       └── policy_patterns.md          # Examples of conditions, validity and override patterns.
│   │   │
│   │   └── sql_generation/
│   │       ├── SKILL.md                        # Procedure and constraints for candidate SQL generation.
│   │       ├── scripts/
│   │       │   └── validate_sql.py             # Deterministic pre-check before runtime SQL guard.
│   │       └── references/
│   │           └── sql_rules.md                # Dialect/semantic generation guidance; not a security boundary.
│   │
│   ├── migrations/
│   │   └── cce_control/
│   │       ├── 001_registry.sql                # Creates `registry` schema and source/ingestion tracking tables.
│   │       ├── 002_metadata.sql                # Creates structured schema/table/column/sample snapshot tables.
│   │       ├── 003_governance.sql              # Creates `governance` proposal/review/approval lifecycle tables.
│   │       ├── 004_context.sql                 # Creates `context` package and governed asset tables.
│   │       ├── 005_runtime.sql                 # Creates `runtime` query/execution tracking tables.
│   │       └── 006_audit.sql                   # Creates append-only `audit` governance/traceability tables.
│   │
│   └── tests/
│       ├── unit/
│       │   ├── connectors/                     # Connector contract/factory/change behavior tests.
│       │   ├── ingestion/                      # Parser, normalization, checkpoint and ingestion tests.
│       │   ├── governance/                     # State transition and approved-only invariant tests.
│       │   ├── context_packages/               # Package version/inheritance/validation tests.
│       │   ├── runtime/                        # Entity, rule, SQL guard and proof-runtime tests.
│       │   ├── skills/                         # SKILL.md schema/dependency/loader tests.
│       │   └── security/                       # Role, entitlement, credential and DLP tests.
│       │
│       ├── integration/
│       │   ├── postgres/                       # Real `cce_control` repository integration tests.
│       │   ├── snowflake/                      # Read-only Snowflake connector integration tests.
│       │   ├── azure_blob/                     # Azure Blob discovery/read integration tests.
│       │   └── agentic_plane/                  # External SDK contract/integration tests.
│       │
│       ├── contract/
│       │   ├── protobuf/                       # Backward-compatibility tests for public protobuf contracts.
│       │   └── mcp/                            # MCP query tool contract tests.
│       │
│       └── e2e/
│           └── test_mvp_flow.py                # End-to-end ingest → govern → package → query → trace MVP proof.
│
├── frontend/
│   └── README.md                               # Placeholder for future Admin, Steward and Query Consumer UI.
│
├── scripts/
│   ├── generate_proto.py                       # Regenerates Python protobuf/gRPC code from backend/proto.
│   ├── migrate_db.py                           # Applies `cce_control` migrations for local/dev environments.
│   ├── verify_snowflake.py                     # Manual Snowflake connector connectivity diagnostic.
│   ├── verify_azure_blob.py                    # Manual Azure Blob connector connectivity diagnostic.
│   └── run_demo_ingestion.py                   # Local MVP ingestion smoke-test entry point.
│
├── deploy/
│   └── docker/
│       └── Dockerfile.backend                  # Production image for the CCE Python gRPC/MCP server.
│
└── docs/
    ├── architecture/
    │   ├── structure.md                        # This target repository structure and responsibility map.
    │   ├── runtime-flow.md                     # Detailed Context ON/OFF query execution sequence.
    │   ├── ingestion-flow.md                   # Structured/unstructured ingestion and AgenticPlane boundary.
    │   └── governance-flow.md                  # Propose/Review/Approve/Reject/Evolve lifecycle.
    │
    ├── decisions/
    │   ├── ADR-001-grpc-protobuf.md             # Decision: protobuf-first gRPC server contract.
    │   ├── ADR-002-cce-control-postgres.md      # Decision: PostgreSQL `cce_control` as CCE control store.
    │   └── ADR-003-agentic-plane-boundary.md    # Decision: graph/vector/retrieval delegated to AgenticPlane.
    │
    └── reference/
        ├── CCE_MVP.pdf                         # MVP active-context-loop source artifact.
        └── Vision_Brief_CCE.docx               # Product vision and architectural principles source artifact.
```

---

## `cce_control` database naming

The application-owned PostgreSQL database is named:

```text
cce_control
```

Recommended PostgreSQL schemas:

```text
cce_control
├── registry      # Sources, source versions, ingestion runs and checkpoints.
├── metadata      # Warehouse schemas, tables, columns and samples.
├── governance    # Proposals, reviews, approvals, rejections and lifecycle history.
├── context       # Workspace context packages, glossary, semantic mappings, policy rules and verified SQL.
├── runtime       # Query runs and structured execution metadata.
└── audit         # Append-only governance and answer trace events.
```

`cce_control` is the authoritative store for **CCE-owned governed state**. It is not the graph/vector store.

---

## AgenticPlane boundary

CCE calls AgenticPlane through:

```text
backend/src/cce/integrations/agentic_plane/
```

This package contains both the external `AgenticPlaneClient` placeholder and
the MVP `LocalIndexClient` pgvector implementation. Callers should select one
through bootstrap/config and keep all index/search calls behind this package.

Expected responsibility split:

```text
CCE                                           AgenticPlane
──────────────────────────────────────        ─────────────────────────────
Source registration                           Chunking
Source/version tracking                       Embeddings
Document normalization                        Vector storage/search
DLP/entitlement enforcement                   Graph extraction
Governance lifecycle                          Graph storage/search
Workspace context packages                    Long-term memory infrastructure
Semantic mappings / verified SQL              Retrieval infrastructure
Query orchestration                           AgenticPlane observability stack
Entity/business-rule reasoning
Guarded enterprise SQL execution
Context ON/OFF proof
Governance traceability
```

CCE must not directly depend on AgenticPlane's PostgreSQL, Redis, ArcadeDB, NATS, LiteLLM, MinIO or Langfuse internals. The local pgvector index is a bounded MVP implementation of the same adapter contract, not access to AgenticPlane internals.

---

## Server surfaces

### gRPC

Primary application/server interface.

```text
QueryService.Query
SourceService.RegisterSource
SourceService.TestConnection
SourceService.TriggerIngestion
SourceService.GetIngestionStatus

GovernanceService.ListProposals
GovernanceService.GetProposal
GovernanceService.ApproveProposal
GovernanceService.RejectProposal

PackageService.GetPackage
PackageService.ListPackages
PackageService.GetPackageVersion
```

The Web UI should eventually consume these protobuf contracts through a browser-compatible gRPC/Connect transport rather than creating a second business API.

### MCP

MCP exposes selected CCE capabilities to external AI agents.

For MVP:

```text
query(...)
    └── calls the same runtime.service.QueryService used by gRPC
```

MCP contains no independent governance, retrieval or query implementation.

---

## User roles supported by backend

```text
ADMIN
    Source configuration, credential references, connection checks,
    first ingestion, re-ingestion and operational source status.

STEWARD
    Review/edit/approve/reject/evolve proposed context assets
    and manage governed package lifecycle.

QUERY_CONSUMER
    Human analyst, application or AI agent consuming approved governed context.
```

Authorization is enforced before service execution, not only in the frontend.

---

## Logging and traceability split

### Engineering observability

Located under:

```text
src/cce/observability/
```

Used for debugging and operations:

```text
DEBUG / INFO / WARNING / ERROR
latency
failures
retries
SDK timings
connector timings
resource metrics
```

This can be configured/toggled by environment.

### Governance traceability

Located under:

```text
src/cce/traceability/
```

Records business/governance facts:

```text
who changed an asset
what changed
approval/rejection
source/version used
package/version used
rule used
approver
rule validity
entity resolution
SQL executed
Context ON/OFF result
answer trace ID
```

Governance traceability may be optional for local development, but should be mandatory in production.

---

## Skills rule

A skill is a bounded reasoning procedure available to one or more agents.

Each skill may contain:

```text
<skill>/
├── SKILL.md       # Purpose, instructions, constraints, dependencies and allowed tools.
├── scripts/       # Deterministic helpers the skill is allowed to execute.
└── references/    # Supporting material loaded only when needed.
```

Skills do not bypass CCE services or governance. A skill can guide reasoning, but deterministic security, approval and SQL execution controls remain code-enforced.

---

## Current repo → target repo cleanup

```text
CURRENT                                         TARGET
──────────────────────────────────────────────  ─────────────────────────────────────────────
agents/ingestion_pipeline.py                    ingestion/service.py
agents/ingestion_workflow.py                    ingestion/orchestrator.py
agents/connector_agent/change_capture.py        ingestion/change_detection/*
agents/connector_agent/* deterministic logic    connectors/* or ingestion/*
common/checkpoint_store.py                      ingestion/checkpoint.py
common/tools/checkpoint_manager.py              ingestion/checkpoint.py
common/tools/credential_loader.py               security/credentials.py
common/tools/dlp_classifier.py                  security/dlp.py
common/tools/document_normalizer.py             ingestion/normalizers/document.py
common/tools/source_connector.py                connectors/base/*
common/known_adapters.py                        connectors/registry.py
common/skill_loader.py                          skills/loader.py
common/correlation.py                           rpc/interceptors/correlation.py
ingestion/azure_blob_source.py                  connectors/unstructured/azure_blob/connector.py
ingestion/file_detection.py                     ingestion/change_detection/documents.py
ingestion/parsers/*                             ingestion/parsers/*
repository/base.py                              persistence/ports.py
repository/postgresql_metadata_repository.py    persistence/postgres/* repositories
schema/*.sql                                    migrations/cce_control/*.sql
prompts/*                                       agent-specific skills/references where applicable
tools/verify_*                                  scripts/verify_*
tools/test_demo_*                               tests/e2e or scripts/run_demo_ingestion.py
resources/*                                     docs/reference/*
requirements.txt                                backend/pyproject.toml
common/                                         removed after migration
```

---

## Dependency direction

```text
gRPC / MCP
    ↓
Application modules
    ↓
Runtime / Ingestion / Governance / Context Packages
    ↓
Core abstractions + persistence ports
    ↓
────────────────────────────────────
Infrastructure implementations
PostgreSQL / Snowflake / Azure Blob / AgenticPlane SDK
```

Rules:

1. `core` imports no connector, database, SDK or transport implementation.
2. `rpc` and `mcp` call application services; they do not contain business logic.
3. `runtime` accesses AgenticPlane only through `integrations.agentic_plane`.
4. `runtime` executes warehouse queries only through structured connector interfaces.
5. `governance.policy` is the central approved-only enforcement boundary.
6. PostgreSQL implementations satisfy interfaces defined in `persistence/ports.py`.
7. Skills may call only explicitly permitted tools/services.
8. No new generic `common/` or catch-all `utils/` directory should be introduced.

---

## MVP query runtime ownership

The target runtime must be able to coordinate:

```text
Request
→ authenticate / authorize
→ trace ID
→ intent
→ AgenticPlane retrieval
→ approved relational context retrieval
→ entity resolution
→ ambiguity resolution
→ package hierarchy resolution
→ business-rule resolution
→ semantic mapping
→ determine live-data requirement
→ verified SQL lookup or candidate SQL generation
→ SQL guard
→ read-only execution
→ apply approved business rules
→ Context ON answer
→ Context OFF baseline
→ proof comparison
→ citations + lineage + package/rule versions
→ governance trace
→ response
```

The exact agent/deterministic split inside this runtime should be designed separately before implementation.

## Implemented evidence boundary update

CCE now owns content-element token chunking and Markdown/metadata rendering in `integrations/agentic_plane/{chunking,rendering}.py`. AgenticPlane continues to own hosted embedding, vector storage and graph infrastructure. Earlier target tables assigning all chunking to AgenticPlane are superseded by this boundary. See the dated evidence update in `IMPLEMENTATION_STATUS.md` for the implemented subset and outstanding workspace/feedback/retry work.
