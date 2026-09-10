# CCE implementation status

This document describes the actual backend implementation, not a hosted production acceptance claim.

## Implemented

- Existing Snowflake, Azure Blob and local filesystem integration paths, parsers, normalizers and structured metadata persistence are retained; PostgreSQL, SQL Server, MySQL and Google Drive connectors were added (see the dated updates below).
- Workspace is the single top-level governance/runtime scope. `Domain` was removed operationally: no `domain`/`domain_id` remain in the schema, repositories, services, LangGraph state, ingestion, protobuf or frontend. Workspace creation is transactional with its one `context_package` row; the first approved proposal batch creates `v1`, subsequent approved batches increment the version.
- PostgreSQL source-item identity, item outcomes, candidate staging and recoverable leased ingestion jobs, all keyed by `workspace_uuid` instead of `domain_id`. `source_domain`/`source_domain_detection` and LLM domain detection were dropped; sources belong to exactly one Workspace (`cce_source.workspace_uuid`, case-insensitive unique `name` per Workspace).
- Source-level LangGraph fan-out, SUCCESS/PARTIAL/FAILED gates (external `COMPLETE` state removed), same-run resume, changed-again processing and missing-source evidence checks.
- SUCCESS-only per-Workspace proposal promotion, exact semantic deduplication, merged evidence, conflict ambiguity, CREATE/UPDATE/REMOVE and NO_CHANGE batches, serialized per Workspace so concurrent source batches cannot produce duplicate package versions.
- Typed seven-kind asset payloads, steward edits, immutable machine proposals, append-only review decisions and automatic terminal-batch package construction.
- Atomic full-snapshot package activation, immutable revisions/history, monotonically increasing integer versions (no semantic versioning), BUILD_BLOCKED and soft retirement. Exactly one package per Workspace; `UNIQUE(workspace_uuid)` is enforced at the database level.
- Relational approved graph projection and manifest-restricted bounded traversal, scoped to the resolved Workspace.
- AgenticPlane 1.3 workspace/source-filtered vector search and source-linked GraphRAG retrieval, supplemented by the active Workspace package context, with explicit insufficient-context behavior. A query with no active approved package version is rejected with a structured `NO_ACTIVE_PACKAGE` 409, never silently answered Context-OFF-only.
- Multi-question atomization: an LLM call splits a compound question into 1-10 standalone atomic questions (validation rejects rather than silently truncating past 10). Each atomic question runs its own full parallel Context ON/OFF LangGraph subgraph, retrieves Workspace-scoped positive/negative feedback as few-shot guidance, and is proven independently; a failed atomic question is reported explicitly rather than fabricated in the final synthesis, which is built only from successful Context ON answers.
- Shared SQL generation/parse/validation/guard/execution/error-description/retry graph; sqlglot guards, per-dialect timeout and row cap; durable attempts and structured query node/final traces.
- Human-readable citations: unstructured evidence renders as `File.pdf - p. 4, paragraph 7`-style labels built from real supplied coordinates (never inferred pages); structured/SQL evidence renders as `<source name> - DATABASE.SCHEMA.TABLE`. Internal IDs remain in the API payload for audit but are never required for the user-facing label.
- Feedback memory: thumbs up/down on the final synthesized answer, optional comment on downvote, an LLM-generated critique (issue category, rationale, confidence) when a downvote has no comment, PostgreSQL persistence of the full governed feedback record (`query_feedback`), and Workspace-scoped semantic retrieval feeding future answering prompts as few-shot positive/negative examples. Feedback embeddings are never a bespoke Postgres `vector` column: eligible feedback is indexed through the same `index_client` boundary (AgenticPlane in production, `LocalIndexClient`/pgvector only in local/offline mode) used for every other embedding, so the control-plane Postgres database never needs the `vector` extension just to support feedback -- notably on managed Postgres services (e.g. Azure Database for PostgreSQL) where that extension is not allow-listed by default. A downvoted answer is never treated as a positive example; low-confidence (`<0.70`) critiques are persisted but excluded from few-shot use (and are never indexed for retrieval).
- Production HTTP and gRPC Workspace-scoped contracts: `POST/GET/PATCH/DELETE /workspaces`, `/source-types`, sources (including pre-registration `/discover`), proposals, package/versions, `/query`, `/feedback` and `/retrieve`. gRPC exposes the same surface through a single `WorkspaceService` action-dispatch RPC backed by `workspaces.proto`; `domains.proto`/`governance.proto`/`packages.proto`/`query.proto`/`retrieval.proto`/`sources.proto` and their per-concept RPC services were removed. The MCP helper delegates to the same Workspace-scoped runtime.
- Frontend is Workspace-first: `/workspaces`, `/workspaces/new`, and nested `/workspaces/:workspaceId/{sources,proposals,package,query}` routes. There is no Domain page, no domain dropdown and no Context ON/OFF toggle; the query result page shows the synthesized governed answer, package name/version, readable citations, thumbs up/down feedback and an expandable panel per atomic question (Context ON, Context OFF, proof, generated SQL, citations, warnings). No internal UUID is rendered as a user-facing identifier.
- Task-model settings and deterministic structured Gemini/LiteLLM calls.

## Validation and practical limits

Lifecycle integration tests use real isolated PostgreSQL databases and explicit model/index/warehouse fixtures. They exercise partial resume, no-change, dedupe/conflicts, evidence-aware removal, immutable history, active-version uniqueness, blocked builds, graph depth, lease fencing, SDK request construction, transport contracts and golden query behavior. Hosted Snowflake/AgenticPlane/LLM end-to-end acceptance and benchmark accuracy remain deployment validation, not inferred from fixture results.

The private AgenticPlane SDK was inspected at version 1.3.0. CCE uses its documented `metadata_filter` keyword and JSONB operators. No AgenticPlane source or infrastructure was modified.

DLP now detects/redacts baseline email, SSN and common phone formats; comprehensive enterprise detection is still partial. Actor role checks exist, but deployment must authenticate actor claims upstream; an identity provider, TLS and full gateway integration are not implemented here. Raw `/retrieve` remains a diagnostic API, not a governed answer API, and must not be exposed as a governed alternative.

New source/query/SQL state values use Pydantic models and thin TypedDict graph state. The standalone legacy ingestion/connector utilities retain earlier contracts for compatibility; production source grounding uses typed outputs and confines raw provider dictionaries to its adapter. Standalone legacy runtime helper stubs are not called by the new orchestrator.

## Intentionally outside this MVP

- Continuous source listeners, CDC, webhooks and automatic rule expiry.
- Cross-Workspace runtime queries, multiple packages per Workspace, semantic package versions, four-tier inheritance and federated database joins.
- CCE data-row authorization beyond the configured warehouse role.
- A LangGraph checkpoint database, Redis/Celery or a CCE graph database.
- A new MCP protocol listener. The existing MCP Python helper is adapted; network MCP transport remains planned.
- Managed Identity for Azure Blob and Entra authentication for SQL Server.
- Oracle, Databricks, BigQuery, S3, SharePoint, OneDrive, Gmail, Slack, Teams, Confluence and vision-model image reasoning (images use OCR text extraction only).
- An external vector database for feedback; feedback metadata is persisted in PostgreSQL and feedback embeddings reuse the existing AgenticPlane/local-index boundary.

See [ingestion](architecture/ingestion-flow.md), [governance](architecture/governance-flow.md), [runtime](architecture/runtime-flow.md), and [implementation report](IMPLEMENTATION_REPORT.md) for operational details.

## Evidence transport update (2026-09-09; partial enhancement delivery)

The shared index chunker now walks normalized content elements and nested children,
retains heading ancestry, and uses `cl100k_base` token counts with configurable
1000-token targets and 125-token textual overlap. Paragraph/line/sentence/word
boundaries are preferred when splitting oversized elements. Small tables render
as one Markdown table; oversized tables split without overlap. Offsets for tables
refer to their rendered Markdown, not physical document byte positions. Small
adjacent elements are not packed together. The original normalized input is not
mutated. Chunk UUIDs include source/document/version/element coordinates and text.
The local index uses those UUIDs for repeat-write upserts; this does not establish
hosted AgenticPlane write idempotency or CDC supersession.

Both index implementations use a common Markdown envelope and retain structured
metadata, including `record_type`, section path, element ID, chunk ID, offsets,
and supplied page/bbox/confidence. Grounding retains supplied parser coordinates
and DOCX parsing preserves paragraph/table order. Governance evidence stores the
retrieved metadata; runtime citations add `coordinates` and a readable `label`.
The existing protobuf branch citation `Struct` supports these additive fields;
no protobuf schema change or database migration was introduced in this update.

PDF extraction now selects RapidOCR per page below
`CCE_PDF_NATIVE_MIN_CHARS` (default 20 alphanumeric characters), preserving native
text on other pages. OCR is injectable behind the parser callback; RapidOCR uses
its ONNX default engine. OCR bounding boxes are rendered-pixel coordinates with
render scale 2 recorded in metadata. No page/element truncation is performed.
An unreadable page fails the document rather than returning silently incomplete
successful evidence. OCR model provisioning and hosted OCR execution are not
validated by the fixture tests.

Workspace models/migration/APIs/ownership, workspace-scoped proposal audit,
feedback memory and atomization (all called out here as not yet implemented at
the time) were completed in the update below. Centralized three-attempt retries
and hosted retry-safe writes/supersession remain outstanding.

## Source connector implementation update - 2026-09-10 (partial refactor)

Implemented the source-connector portion of the new specification:

- `sources/catalog.py` defines the six production source types and strict Pydantic
  configuration schemas, including authentication choices and All/selected schema
  validation. `/source-types` exposes the catalog and JSON schemas for forms.
- `ConnectorFactory.create_source` builds the existing structured/unstructured
  abstractions from typed catalog configurations. The existing source service can
  construct these connectors; the registration contract remains the old contract.
- PostgreSQL, SQL Server and MySQL share a DB-API implementation with injected
  drivers, metadata discovery, read-only execution controls, timeouts and row caps.
  The shared SQL AST guard remains authoritative; row bounds render in the selected
  dialect, including SQL Server TOP. Runtime metadata selects the source dialect.
- Snowflake supports password and encrypted key-pair credential references, plus
  schema discovery. The typed factory enables its existing read-only write probe.
- Azure supports service-principal client construction, configured prefix and
  recursion checks, and connection-string authentication.
- Google Drive uses read-only service-account credentials, scoped folder/shared-drive
  inventories, pagination, ancestry checks on fetch, and transient Docs/Sheets/Slides
  exports. Grounding uses the exported filename suffix for existing parsers.
- Multi-schema grounding re-runs discovery for All selection and excludes internal
  schemas. Selected schemas must be accessible; removed selections are excluded
  from runtime schema context.

New dependencies: `mysql-connector-python>=9,<10`, `pyodbc>=5,<6`, and explicit
`google-auth>=2,<3`. SQL Server requires Microsoft ODBC Driver 18 for SQL Server
installed on the host (and unixODBC on Linux). PostgreSQL uses existing psycopg2.
Google native exports use the Drive files.export endpoint; provider export-size
limits can cause an item failure rather than persisting an exported copy.

The six READY entries mean executable connectors exist; hosted authentication,
permissions and data accuracy have not been accepted through live tests.

## Workspace refactor completion - 2026-09-10

The Domain-to-Workspace MVP refactor described throughout this document is now
complete:

- Migration `014_workspace_scope.sql` renames `domain`->`workspace` (and
  `domain_id`->`workspace_uuid`) across `cce_source`, `candidate_extraction`,
  `proposal_batch`, `context_asset`, `context_package`, `graph_entity`,
  `graph_edge` and `query_trace`; drops `source_domain`/`source_domain_detection`
  and the `DOMAIN_UNRESOLVED`/`detected_domains` ingestion state; normalizes
  ingestion status to `RUNNING`/`SUCCESS`/`PARTIAL`/`FAILED`; and adds the
  `query_feedback` table (metadata only -- no `vector` extension or column; see
  the feedback bullet above). It fails clearly rather than guessing ownership
  when a source has an ambiguous or missing domain association.
- `backend/src/cce/governance/models.py`, `persistence/postgres/workspace_repository.py`,
  `workspaces/operations.py`, `http/app.py` and `rpc/services/workspace_service.py`
  implement Workspace creation (`{name}_workspace`, immutable, case-insensitive
  unique), the one-package-per-Workspace invariant, and the full Workspace-scoped
  HTTP/gRPC surface listed above.
- `sources/catalog.py` and `connectors/` implement all six production source
  types (Snowflake password/key-pair, PostgreSQL, SQL Server, MySQL, Azure Blob,
  Google Drive) with pre-registration discovery, schema selection (`all`/
  `selected`, system schemas excluded) and Google-native Docs/Sheets/Slides
  transient export.
- `runtime/compound.py` implements multi-question atomization and per-atomic-
  question dual-path execution; `runtime/feedback.py` implements feedback
  persistence/retrieval; `runtime/citations.py` and `runtime/orchestrator.py`
  build human-readable unstructured and structured citation labels.
- `frontend/src/routes/AppRoutes.tsx` implements the Workspace-first UI with no
  Domain concept and no visibly rendered UUIDs.

See `docs/decisions/ADR-005-workspace-replaces-domain.md` for the architectural
rationale, and the Tests section of `IMPLEMENTATION_REPORT.md` for how this was
verified.
