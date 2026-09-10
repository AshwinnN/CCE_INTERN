# Governed lifecycle implementation report

## Implemented behavior

The Snowflake saved-config compatibility path converts legacy `schema` to
`schema_selection` and supplies the historical key-pair authentication default.
The production catalog factory disables the temporary-table write probe while
retaining `read_only_verified=False`; guarded SELECT queries remain executable.
Live verification against the configured Snowflake source returned 3,000 rows
for `COUNT(*)` on `ERP_COS_APPAREL.ITEM_VARIANTS`. Compound-query final synthesis
now uses a typed `SynthesisRequest`, matching the shared LLM client contract.
The full live question "How large is the companys product matrix?" completed
successfully in both Context ON and Context OFF, each returning 3,000 item
variants, with successful final synthesis. Audit trace:
`663eff9e-715c-43d9-b213-9e677b32d464` (2026-09-10). No migrations or ingestion
workers were run for this verification. Local regression tests were added but
were not used as acceptance evidence; verification used the live configured
Azure PostgreSQL, Snowflake and LLM services.

Real backend services now connect durable source ingestion to staged extraction, steward review, full Workspace context-package snapshots, package-filtered evidence retrieval, parallel Context ON/OFF answering, guarded SQL with repair, and durable traces. The `frontend/` UI is the real Workspace-scoped production frontend, not a mock; the earlier `backend/api/` development mock has been removed.

The final decision in a batch triggers deterministic validation and atomic activation. Partial ingestion cannot expose proposals. Rejected, no-change and structurally blocked batches do not increment versions. Approved removals retire assets only after successful package creation and preserve historical versions.

Expired job claims cannot finalize runs; indexed document identities also include the claim token to isolate stale workers. SQL scope validation respects quoted identifier casing.

## Important files

| Responsibility | Files under `backend/src/cce/` |
|---|---|
| Composition/configuration | `bootstrap.py`, `main.py`, `config/settings.py` |
| Source workflow | `ingestion/source_graph.py`, `ingestion/grounding.py`, `ingestion/lifecycle_models.py`, `ingestion/job_runner.py`, `sources/service.py`, `sources/models.py` |
| Models/review | `context_packages/models/assets.py`, `governance/models.py`, `governance/service.py`, `governance/state_machine.py` |
| Package lifecycle | `context_packages/builder.py`, `context_packages/validator.py`, `context_packages/service.py` |
| Governed state | `persistence/postgres/{lifecycle_db,workspace_repository,source_repository,ingestion_repository,job_repository,governance_repository,context_repository,runtime_repository,metadata_repository}.py` |
| Query/SQL | `runtime/models.py`, `runtime/orchestrator.py`, `runtime/compound.py`, `runtime/feedback.py`, `runtime/citations.py`, `runtime/sql_pipeline.py`, `runtime/sql_guard.py`, `runtime/sql_executor.py` |
| External boundaries | `integrations/llm/client.py`, `integrations/agentic_plane/client.py`, `integrations/agentic_plane/local_index.py`, `connectors/structured/snowflake/connector.py`, `connectors/structured/relational.py`, `connectors/unstructured/google_drive/connector.py` |
| Sources | `sources/catalog.py`, `sources/service.py`, `sources/models.py`, `connectors/factory.py` |
| Transports | `http/app.py`, `workspaces/operations.py`, `rpc/services/workspace_service.py`, `rpc/server.py`, `mcp/tools/query.py` |
| DLP | `security/dlp.py` |

Protobuf: `backend/proto/cce/v1/{common,health,workspaces}.proto`. `domains.proto`/`governance.proto`/`packages.proto`/`query.proto`/`retrieval.proto`/`sources.proto` and their per-concept RPC services were removed; all Workspace-scoped operations (sources, proposals, package, query, feedback, retrieve) now flow through a single `WorkspaceService` action-dispatch RPC in `workspaces.proto`. Python bindings were regenerated using `scripts/generate_proto.py`; generated files follow the repository's existing ignore policy and must be regenerated in a clean checkout/build.

Tests: `backend/tests/integration/lifecycle/`, updated HTTP response/SDK metadata-filter tests, DLP tests and isolated configuration/source-response tests. Existing Azure smoke testing now requires explicit opt-in.

## Migrations

- `012_domain_governance_lifecycle.sql`: domains, source items/detection, candidate staging, proposal batches/proposals/audit, immutable assets/revisions, evidence links, packages/manifests/snapshots and relational graph projections.
- `013_runtime_and_jobs.sql`: ingestion statuses, one resumable run per source, item outcomes, leased jobs, query/node traces and SQL attempts.

Both are registered in the existing migration runner. Existing migrations were not semantically rewritten. Existing duplicate unfinished legacy source runs must be resolved before applying the new unique index; the migration does not discard them silently.

## Configuration

Both `.env.example` files include:

| Setting | Default |
|---|---|
| `CCE_INGESTION_MAX_CONCURRENCY` | 5 |
| `CCE_DOMAIN_DETECTION_MIN_CONFIDENCE` / `CCE_DOMAIN_MIN_CONFIDENCE` | 0.70 |
| `CCE_DOMAIN_MAX_MATCHES` | 3 |
| `CCE_RETRIEVAL_TOP_K` / `CCE_RETRIEVAL_OVERSAMPLE_FACTOR` | 10 / 3 |
| `CCE_RETRIEVAL_MIN_SCORE` | 0.70 |
| `CCE_GRAPH_MAX_HOPS` | 2 |
| `CCE_SQL_GENERATION_ENABLED` | true |
| `CCE_SQL_MAX_RETRIES` | 2 (three total attempts) |
| `CCE_SQL_TIMEOUT_SECONDS` / `CCE_SQL_MAX_ROWS` | 30 / 1000 |
| `CCE_CONTEXT_OFF_ENABLED` / `CCE_QUERY_INCLUDE_ROWS` | true / true |
| `CCE_JOB_LEASE_SECONDS` / `CCE_JOB_POLL_SECONDS` | 120 / 2 |
| `CCE_LLM_DOMAIN_MODEL`, `CCE_LLM_EXTRACTION_MODEL`, `CCE_LLM_SQL_MODEL`, `CCE_LLM_ANSWER_MODEL`, `CCE_LLM_PROOF_MODEL` | fall back to `CCE_LLM_MODEL` |

Dependencies add sqlglot; AgenticPlane >=1.3 uses the inspected metadata-filter API. Gemini integration is updated to the LangChain-core-compatible 4.x provider package while preserving Gemini and LiteLLM support. Registry authentication was temporary and was not added to the repository.

## API and graph changes

HTTP is fully Workspace-scoped: `POST/GET/PATCH/DELETE /workspaces[/{workspace_id}]`, `GET /source-types`, `/workspaces/{workspace_id}/sources[/discover|/{resource_id}[/test|/ingest]]`, `/workspaces/{workspace_id}/ingestion-runs/{resource_id}`, `/workspaces/{workspace_id}/proposals[/{resource_id}[/approve|/reject]]`, `/workspaces/{workspace_id}/package[/versions[/{resource_id}]]`, `POST /workspaces/{workspace_id}/query`, `POST /workspaces/{workspace_id}/feedback` and `POST /workspaces/{workspace_id}/retrieve`. `/query` takes no domain/context-toggle parameter; it always executes the full dual-path atomized flow and returns `NO_ACTIVE_PACKAGE` (409) when the Workspace has no active approved package version.

gRPC exposes the identical action set through one `WorkspaceService` RPC (`workspaces.proto`'s `WorkspaceRequest{workspace_id, resource_id, actor, payload}` / `WorkspaceResponse{data}`), dispatched by the same `workspaces/operations.py::Operations.execute` boundary the HTTP adapter uses -- there is no separate DomainService/GovernanceService/PackageService/QueryService/RetrievalService/SourceService RPC anymore. The MCP Python helper accepts a Workspace id and delegates to the same Workspace-scoped runtime.

Source graph nodes (`ingestion/source_graph.py`): `discover_and_diff_inventory`, `process_item` via Send, `aggregate_item_results`, `promote_staged_candidates`. Item processing includes grounding, Workspace-scoped indexing/search and one typed extraction per item/Workspace -- there is no domain-detection step.

Compound query graph nodes (`runtime/compound.py`, the entry point for `POST /workspaces/{workspace_id}/query`): `create_query_trace`, `atomize_question` (LLM splits the question into 1-10 standalone atomic questions; validation rejects rather than truncating past 10), a `Send` fan-out to `answer_atomic_question` per atomic question (each retrieves Workspace-scoped feedback lessons, then runs the full per-atomic orchestrator graph below), `final_synthesis` (synthesizes only successful Context ON answers; a failed atomic question is reported, never fabricated), `persist_final_trace`.

Per-atomic-question orchestrator graph nodes (`runtime/orchestrator.py`): `create_trace`, `parse_question`, `load_active_package`, parallel `context_on_subgraph`/`context_off_subgraph`, `proof_classifier`, `persist_trace_finalizer`. There is no `resolve_domain` node; the Workspace is resolved once, by the compound graph, from the URL-scoped `workspace_id`.

Branch nodes: `retrieve_and_assemble`, `resolve_data_source` (chooses among a Workspace's structured sources when more than one is schema-relevant), `run_sql_subgraph`, `answer`. SQL nodes: `generate_sql`, `parse_sql`, `validate_sql`, `guard_sql`, `execute_sql`, `describe_sql_error`, `persist_attempt`.

## Verification

A disposable PostgreSQL instance was installed under `/tmp`. Integration fixtures create/drop uniquely named test databases and replay migrations; they do not truncate an application database.

Executed:

```sh
python scripts/generate_proto.py
python -m compileall -q backend/src/cce
python -m pip check
PYTHON_DOTENV_DISABLED=1 CCE_TEST_DATABASE_URL='<disposable PostgreSQL DSN>' \
  CCE_METADATA_REPOSITORY_ENABLED=false CCE_SNOWFLAKE_LIVE_TESTS=false \
  PYTHONPATH=backend/src python -m pytest backend/tests/unit backend/tests/integration -o addopts='' -q
```

Regression result: **251 passed, 7 skipped**. Skips include explicit live-provider gates and legacy optional skill checks. Deprecation warnings remain in existing parser datetime defaults and TestClient dependencies. The SDK filter test exercises actual AgenticPlane 1.3 protobuf request construction without network calls. The golden query test uses real PostgreSQL state and explicit model/warehouse fixtures, and verifies ON-only approved context, independent SQL execution, citations and external row hiding.

## Remaining deployment work and limits

No hosted end-to-end acceptance or accuracy benchmark was claimed. Deployments still need configured source/LLM/AgenticPlane endpoints and credentials, PostgreSQL migration rollout, authenticated actor claims, and transport security. Baseline DLP is not exhaustive. A network MCP listener and a production-connected frontend remain outside this change; the helper and mock UI boundaries are documented.

The OFF baseline does not invent a standard SLA threshold absent from raw schema/data. In the golden test it reports the current metric and the missing threshold; ON applies the governed exception. A fixture returning NO against a threshold unavailable to OFF would misrepresent the required baseline isolation.

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

**Not implemented by this update:** Workspace models/migration/APIs and ownership,
workspace snapshot/proposal audit and delta generation, feedback memory, centralized
three-attempt retries, and hosted retry-safe writes/supersession. Source-level
proposal promotion remains in place. Existing runtime governance behavior was not
redesigned or newly certified. These are outstanding requested work, not completed
acceptance criteria.

### Evidence update verification

Commands executed from the repository root using `.venv/Scripts/python.exe`:

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
.venv/Scripts/python.exe scripts/generate_proto.py
.venv/Scripts/python.exe -m compileall -q backend/src/cce
.venv/Scripts/python.exe -m pytest backend/tests/unit backend/tests/integration -o addopts='' -q
git diff --check
```

Result: **264 passed, 17 skipped**. PostgreSQL lifecycle fixtures skipped because
`CCE_TEST_DATABASE_URL` is unset; Docker's Linux engine was unavailable. Therefore
this run does not prove database lifecycle acceptance. Earlier focused unit plus
lifecycle invocation: **244 passed, 15 skipped**. Existing dependency and
deprecation warnings remain. New tests cover recursive chunk boundaries, token
budgets/overlap, atomic and oversized tables, version-aware IDs, Markdown
metadata, semantic/PDF citation labels, and mixed/native PDF OCR selection.

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

This is **not the completed Workspace refactor**. Domain ownership, the existing
registration/routes/protobuf contracts, package lifecycle and frontend are still
operationally present. No Workspace migration, Workspace isolation, atomization,
pgvector feedback, or Workspace frontend was introduced by this update. Ingestion
still uses COMPLETE and domain detection. These remain outstanding requested work.
The six READY entries mean executable connectors exist; hosted authentication,
permissions and data accuracy have not been accepted through live tests.

### Connector update validation

With `PYTHON_DOTENV_DISABLED=1`, ran:

```text
.venv/Scripts/python.exe -m pytest backend/tests/unit backend/tests/integration -o addopts='' -q
.venv/Scripts/python.exe scripts/generate_proto.py
.venv/Scripts/python.exe -m compileall -q backend/src/cce
git diff --check
```

Result: **280 passed, 17 skipped**. New injected-driver tests cover strict config
validation, catalog membership, schema rediscovery/system filtering, relational
query guards/timeouts/caps, Snowflake password credentials, scoped Drive exports,
shared-drive pagination, and T-SQL limits. PostgreSQL-backed lifecycle tests still
skip without `CCE_TEST_DATABASE_URL`; live-provider tests remain opt-in. No
Workspace migration or protobuf contract change was made in this partial update.

Provider references: [Drive download/export API](https://developers.google.com/workspace/drive/api/guides/manage-downloads),
[PostgreSQL session settings](https://www.postgresql.org/docs/current/runtime-config-client.html),
and [MySQL execution timeout settings](https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html#sysvar_max_execution_time).

## Workspace refactor completion - 2026-09-10

The prior update's working tree already carried a substantially complete
Domain-to-Workspace rewrite (Workspace model/repository/service/API, the
`014_workspace_scope.sql` migration, `runtime/compound.py` atomization and
`runtime/feedback.py` pgvector feedback), but it was uncommitted, undocumented,
and had five stale test files plus a handful of latent bugs left over from the
mechanical rename. This update closed those gaps:

- Fixed a real production bug in `ingestion/source_graph.py`: `workspace_uuid`
  read back from `IngestionRepository.workspace()` was a plain `str` (psycopg2
  has no UUID typecaster registered here) and was compared directly against
  `Candidate.workspace_uuid` (a pydantic `UUID`), so `str != UUID` always
  evaluated true and every LLM-extracted candidate was rejected as
  `"Extraction crossed workspace or attempted removal"`. Ingestion would have
  silently discarded all extraction candidates in production. Fixed by
  coercing to `UUID` before the comparison.
- Fixed `persistence/postgres/metadata_repository.py::ensure_source`, which
  still queried the pre-migration `adapter` column (`source_type` after
  migration 014) and could fall back to an anonymous `account_id`-based
  `INSERT` that would violate the new `workspace_uuid NOT NULL` constraint.
  Anonymous/legacy source registration was an explicitly removed concept (see
  ADR-005); `ensure_source` now only resolves an already Workspace-registered
  source UUID and raises clearly otherwise.
- Added a structured/SQL citation `label` (`"<source name> - DATABASE.SCHEMA.TABLE"`)
  in `runtime/orchestrator.py::answer`; it previously set `tables`/`database`/
  `schema_name` but no human-readable label, so the frontend fell back to a
  generic "Source evidence" string for every SQL-backed answer.
- Dropped the dead `query_trace.context_on`/`context_off` jsonb columns in
  migration `014_workspace_scope.sql` (superseded by the `response` jsonb
  column added in the same migration; never written to since).
- Fixed a frontend Workspace-UUID leak (`<p>{workspaceId}</p>` on the Query
  page) and several `?`-corrupted characters (thumbs-up/down buttons, `...`
  ellipses, `-` separators) in `frontend/src/routes/AppRoutes.tsx`.
- Removed dead frontend files left over from before the Workspace rewrite,
  confirmed unreferenced from `App.tsx`/`AppRoutes.tsx`: `pages/LoginPage.tsx`,
  `pages/PageHeader.tsx`, `layout/{AppLayout,Header,Footer}.tsx`,
  `components/{Button,EmptyState,Feedback,Field,Loader,Modal,StatusBadge}.tsx`,
  `config/auth.ts`, and the empty `pages/{domains,ingestion,packages,proposals,query,sources}/` directories.
- Rewrote the five test files left importing deleted modules or stale schema:
  `tests/integration/lifecycle/{test_runtime,test_golden_query,test_graph_and_transports}.py`
  (deleted `*_pb2`/RPC-service imports, `WorkspaceCandidate(s)`/`WorkspaceResolution`
  types), `tests/integration/test_http_adapter.py` (flat pre-Workspace routes),
  and `tests/unit/sources/test_source_service.py` (a since-removed synchronous
  local-fs ingestion API). Deleted `tests/unit/rpc/test_retrieval_rpc_service.py`
  (tested a global, non-Workspace-scoped retrieval RPC that no longer exists and
  would violate the Workspace isolation requirement) and
  `tests/unit/persistence/test_source_repository.py` (mocked literal SQL text
  from a pre-Workspace schema); added a real-Postgres replacement,
  `tests/integration/lifecycle/test_source_repository.py`, and fixed the
  `adapter`/`account_id` column references and missing `workspace_uuid` in
  `tests/integration/lifecycle/test_registered_source_metadata.py` and
  `tests/integration/postgres/test_postgresql_{metadata_repository,integration}.py`.
- Added `docs/decisions/ADR-005-workspace-replaces-domain.md` and brought this
  report, `IMPLEMENTATION_STATUS.md`, and `README.md` current.

### Verification

Backend, against a disposable `pgvector/pgvector:pg16` container
(`CCE_TEST_DATABASE_URL` set, `CCE_METADATA_REPOSITORY_ENABLED` unset):

```sh
python -m pytest tests/ -q
```

All tests pass except three pre-existing failures unrelated to this refactor
(not touched by it, and reproducible before these changes): a concurrency race
in `test_lifecycle.py::test_conflict_edit_audit_blocked_all_rejected_and_concurrent_run`
(four threads racing `create_or_resume` under `FOR UPDATE`), and two
`tests/unit/integrations/test_llm_client.py` tests that require a live
LiteLLM/OpenAI-compatible endpoint with a valid virtual key (401 in this
environment). Frontend: `npm run build` (`tsc -b && vite build`) succeeds with
no errors after the dead-file cleanup above.

### Remaining limitations

- The pre-existing `test_conflict_edit_audit_blocked_all_rejected_and_concurrent_run`
  concurrency race and the two credential-gated `test_llm_client.py` tests were
  not fixed; they are outside this refactor's scope.
- `sources/service.py::discover`/`update`/`test_connection` and the Google
  native-export path are exercised by earlier connector-update tests, not by
  new tests added in this pass; they were verified by code review against the
  spec, not by new automated coverage.
- No live Snowflake/PostgreSQL/SQL Server/MySQL/Azure Blob/Google Drive
  credentials were exercised; connector correctness against real services
  remains a live/opt-in test concern, as it was before this update.

## Feedback embedding boundary correction - 2026-09-10

Starting the server against a real target database (`python -m cce.main`
pointed at an Azure Database for PostgreSQL Flexible Server instance) surfaced
`psycopg2.errors.FeatureNotSupported: extension "vector" is not allow-listed
for "azure_pg_admin" users`, raised from migration 014's unconditional
`CREATE EXTENSION IF NOT EXISTS vector;`.

This was not an Azure-only problem to work around -- it was a real regression
against an established codebase convention. `migrations.py::migration_paths()`
already treats `008_local_index.sql`/`009_local_index_exact_search.sql` (and
the `vector` extension they would install) as strictly opt-in, skipped
whenever `CCE_INDEX_BACKEND` is not `local`; `apply_control_schema` even has a
dedicated, actionable error message for exactly this ("pgvector extension is
required for local indexing... or set CCE_INDEX_BACKEND=agentic_plane").
Migration 014's `query_feedback.embedding vector(768)` column and
unconditional `CREATE EXTENSION` broke that convention: it made every
deployment need pgvector just to support feedback, including
`agentic_plane`-backed deployments that otherwise never touch pgvector.

Separately, `bootstrap.py` constructed `FeedbackService` with
`LocalIndexClient(settings.database_url)._embed` unconditionally -- reaching
past the already-selected `index_client` (AgenticPlane or LocalIndexClient
depending on `settings.index_backend`) to always build a second, redundant
`LocalIndexClient` purely to borrow its private embedding method, regardless
of which backend was actually configured.

Fix: `runtime/feedback.py::FeedbackService` no longer computes or stores a raw
embedding at all. Eligible feedback (`lesson_eligible`) is indexed through
`self.index_client.index(...)` -- the same boundary already used for every
other embedding in the system (`AgenticPlaneClient` in production,
`LocalIndexClient` only in local/offline mode) -- with the question as the
searchable content and the rating/lesson text carried in metadata.
`FeedbackService.retrieve()` calls `self.index_client.search(...)` with a
`{workspace_uuid, kind: 'feedback', lesson_eligible: true}` metadata filter
and builds the few-shot label directly from the hit's metadata, with no
Postgres join needed on the retrieval hot path. `query_feedback` (Postgres)
keeps the full governed audit record (rating, comment, question, answer,
citations, context, critique, confidence) exactly as specified, minus the
`embedding` column. `bootstrap.py` now passes the already-constructed
`index_client` into `FeedbackService` instead of building a redundant one.
Migration `014_workspace_scope.sql` no longer creates the `vector` extension
or an `embedding` column.

Data-side root cause of the *first* migration failure the user hit (before
reaching the pgvector one): migration 014's own safety check
(`RAISE EXCEPTION 'Workspace migration requires exactly one existing domain
association per source...'`) was working as specified (spec section 37: "fail
migration clearly rather than silently assigning incorrect ownership"). The
target Azure `cce_metadata` database had one Snowflake source registered but
never ingested, with zero `source_domain` rows. Per the user's direction, it
was linked to the database's one existing domain ("ERP Context System") via a
manual `source_domain` row (with a placeholder `cce_ingestion_run` row to
satisfy the FK, since the source had never actually been ingested) before
re-running the migration -- not by weakening the check.

### Verification

Re-ran the full backend suite against the disposable `pgvector/pgvector:pg16`
container plus four new `tests/integration/lifecycle/test_feedback.py` tests
(upvote persistence + retrieval; downvote-with-comment skips the LLM call;
downvote-without-comment confidence gate, `>=0.70` indexed vs `<0.70`
persisted-but-excluded; Workspace-scoped retrieval that never returns another
Workspace's feedback or treats a downvote as a positive example) added because
no `FeedbackService` test existed before this correction. All pass; the same
three pre-existing, unrelated failures noted above remain unchanged.
