# CCE Repository Guide for Coding Agents

## Truth hierarchy

Use these sources in this order when reasoning about the repository:

1. **Source code** — what is implemented now.
2. `docs/architecture/structure.md` and `docs/decisions/` — intended code architecture and boundaries.
3. `docs/reference/Vision_Brief_CCE.docx`, `docs/reference/CCE_MVP.pdf`, and `docs/reference/context_architecture.png` — product intent and invariants.

Do not infer implementation from a folder name, proto field, ADR, architecture diagram, or Vision statement. Stub code is not implemented behavior.

## System purpose

CCE is intended to sit between enterprise sources and AI consumers as a governed context boundary. The target product ingests structured and unstructured evidence, requires human approval before context becomes usable, assembles versioned domain packages, executes Context OFF and Context ON paths, attaches traceability, and exposes the same governed runtime through gRPC/HTTP/MCP.

**Current repository reality:** source connection, parsing/normalization, structured metadata persistence, protobuf contracts, gRPC server assembly, and a thin HTTP adapter have meaningful implementation. The governance → package → runtime → trace → MCP product path is not yet implemented.

## Module map

| Module | Responsibility in this repo | Status | Primary entry point / evidence |
|---|---|---|---|
| `backend/proto/cce/v1` + `backend/src/cce/gen/cce/v1` | Public gRPC contracts and generated bindings | **IMPLEMENTED** | `query.proto`, `sources.proto`, `governance.proto`, `packages.proto` |
| `backend/src/cce/rpc` | gRPC server and transport mappings | **PARTIAL** | `rpc/server.py::create_server()` |
| `backend/src/cce/http` | Thin FastAPI adapter over `Application` | **PARTIAL** | `http/app.py::create_app()` |
| `backend/src/cce/connectors` | Connector contracts, registry, routing, observation, Snowflake access | **PARTIAL** | `connectors/agent.py::ConnectorAgent.handle()` |
| `backend/src/cce/ingestion` | Connector event → fetch → parse/normalize → DLP hook → metadata/SDK emit → checkpoint | **PARTIAL** | `ingestion/service.py::run_pipeline()`, `ingestion/orchestrator.py::run_ingestion()` |
| `backend/src/cce/persistence` | `cce_control` source/structured-metadata persistence and migrations | **PARTIAL** | `PostgreSQLMetadataRepository`, `PostgresSourceRepository` |
| `backend/src/cce/security` | Credential resolution plus security boundary placeholders | **PARTIAL** | `security/credentials.py::load_credential()` |
| `backend/src/cce/governance` | Proposal/review/approval lifecycle | **PLANNED** | service methods return empty/`NOT_FOUND`; `003_governance.sql` is schema-only |
| `backend/src/cce/context_packages` | Governed package assembly/versioning/inheritance | **PLANNED** | service is placeholder; `004_context.sql` is schema-only |
| `backend/src/cce/runtime` | Governed query reasoning, SQL, Context OFF/ON proof | **PLANNED** | `runtime/service.py::QueryService.query()` returns a not-implemented answer |
| `backend/src/cce/traceability` | Answer/governance trace persistence | **PLANNED** | `TraceabilityService.record()` is pass-through; `006_audit.sql` is schema-only |
| `backend/src/cce/mcp` | MCP exposure of the CCE runtime | **PLANNED** | `create_mcp_server()` returns a Python dict, not an MCP server |
| `backend/src/cce/integrations` | AgenticPlane and Gemini boundaries | **PARTIAL** | Gemini client is functional but disconnected; AgenticPlane `retrieve()` returns `[]` |
| `backend/skills` + `backend/src/cce/skills` | Versioned agent instructions/helpers and dynamic loader | **PARTIAL** | skill assets exist; no production runtime loads them |
| `backend/src/cce/observability` | Engineering logging/metrics/tracing | **PARTIAL** | logging helper exists; metrics/tracing are no-ops |
| `frontend` | Analyst/steward UI | **PLANNED** | `frontend/README.md` only |

Detailed status: `docs/IMPLEMENTATION_STATUS.md`.

## Main execution entry points

### Server path — current

```text
python -m cce.main
  -> config.settings.load_settings()
  -> bootstrap.build_application()
       -> optional cce_control migrations
       -> constructs QueryService/GovernanceService/ContextPackageService
       -> constructs PostgresSourceRepository/PostgreSQLMetadataRepository
  -> optional FastAPI thread: http.app.create_app()
  -> rpc.server.serve()
       -> Health / Source / Query / Governance / Package gRPC handlers
```

Important asymmetry: `SourceRPCService.TriggerIngestion()` and the matching HTTP endpoint do **not** invoke the real ingestion pipeline; both return `NOT_IMPLEMENTED`/`NOT_STARTED`.

### Ingestion path — current, callable outside the server source API

```text
ConnectorRequest
  -> ConnectorAgent.handle()
  -> change event(s)
  -> ingestion.service.run_pipeline()
  -> ingestion.orchestrator.run_ingestion()
       -> fetch structured or unstructured content
       -> structured metadata persistence OR document parsing
       -> normalize
       -> DLP classify/redact hook
       -> emit to CCE_SDK_ENDPOINT (or dry-run if unset)
       -> file-backed ingestion checkpoint
```

See `backend/src/cce/ingestion/FLOW.md`.

## Dependency direction actually present

```text
main
  -> bootstrap
      -> application services + PostgreSQL repositories

rpc/http
  -> Application
      -> services/repositories

mcp
  -> runtime.service

runtime
  -> integrations.agentic_plane + domain-neutral runtime helpers

context_packages
  -> governance.policy (approval helper)

ingestion
  -> connectors + security.dlp + persistence

connectors
  -> security.credentials + provider SDKs
```

Do not introduce reverse dependencies from connectors/persistence into runtime, governance, transport, or MCP.

## Shared models and contracts

- Public API: `backend/proto/cce/v1/*.proto`. Generated files under `backend/src/cce/gen/cce/v1/` must not be edited manually.
- Runtime request/response: `backend/src/cce/runtime/service.py::{QueryRequest, QueryResponse}`.
- Connector request/response/change-event contracts: `backend/src/cce/connectors/contracts.py`.
- Canonical ingestion document/schema models: `backend/src/cce/ingestion/models.py`.
- Structured persistence contract: `backend/src/cce/persistence/ports.py::MetadataRepository`.
- Domain-neutral core types: `backend/src/cce/core/`.

Proto fields describe intended payload capacity; they do **not** prove backing behavior exists.

## Repository-wide conventions discovered from code

- Python packaging is defined by `backend/pyproject.toml`; there is no primary `requirements.txt`.
- External I/O is commonly dependency-injected for tests (`driver_connect`, object/catalog listers, fetchers, SDK emitter, repositories). Preserve this when adding provider or workflow code.
- Structured metadata uses deterministic IDs for stable entities plus immutable snapshot-scoped rows. Do not replace that with mutable latest-state tables without an explicit architecture change.
- Provider-specific environment parsing is kept near the provider (`connectors/structured/snowflake/config.py`); generic connector layers should not hardcode provider environment variable names.
- Public protobuf source is under `backend/proto/cce/v1/`; generated code under `backend/src/cce/gen/cce/v1/` is generated output.
- Transport adapters should be thin. The same `Application` service objects are shared by gRPC and HTTP; MCP is intended to follow the same pattern.
- Placeholder modules return neutral/default values or raise `NotImplementedError`; do not treat these return shapes as established business behavior.
- Tests use fake/injected provider boundaries for unit coverage and environment-gated live integration tests where present.

## Common change surfaces

| Task | Usually inspect/modify first | Normally avoid unless contract crosses boundary |
|---|---|---|
| Add structured connector | `connectors/structured/<adapter>/`, `connectors/factory.py`, registry after implementation | governance/runtime/MCP |
| Add parser/file type | `ingestion/parsers/`, `ParserFactory` | connectors registry, runtime |
| Change structured metadata | ingestion persistence node + `persistence/ports.py` + Postgres repo/migration | frontend and MCP |
| Implement proposal approval | `governance/` + governance repository/migration | provider/parser internals |
| Implement package versioning | `context_packages/` + context repository/migration | source discovery |
| Implement query/proof | `runtime/` + package/governance/trace contracts | parser internals |
| Change public API | proto + matching transport + backing service | duplicate business logic in transport |

## Critical invariants and current enforcement

| Invariant | Required by target | Current enforcement |
|---|---|---|
| Domain-blind core | Yes | **PARTIAL:** current `backend/src` contains no verified hardcoded business-domain terms, but there is no automated enforcement. |
| Machine proposes; human approves | Yes | **NOT ENFORCED / PLANNED:** governance service/persistence are placeholders. |
| Only approved context is served | Yes | **PARTIAL helper only:** `governance/policy.py::require_approved()` and `context_packages/builder.py::assert_assets_approved()` exist, but no active governed runtime invokes them. |
| Source provenance retained | Yes | **PARTIAL:** ingestion events/canonical metadata carry source identity/version; answer-level lineage is absent. |
| Read-only structured source access | Yes | **IMPLEMENTED for Snowflake connection:** `SnowflakeConnector.connect()` performs a live `CREATE TEMPORARY TABLE` write probe and rejects credentials when it succeeds. |
| SELECT-only guarded execution | Yes | **NOT ENFORCED end-to-end:** `runtime/sql_guard.py::enforce_select_only()` only checks a prefix and is not called by `SnowflakeConnector.execute_query()`. |
| Statement timeout and row cap | Yes | **NOT ENFORCED at query execution:** config fields exist; runtime executor is a stub; `execute_query()` fetches all returned rows. |
| DLP/PII before candidate knowledge | Yes | **NOT ENFORCED:** ingestion calls the hook, but `security/dlp.py` deliberately returns PUBLIC and redaction is a no-op. |
| Entitlements captured/enforced | Yes | **NOT ENFORCED:** helper exists but active retrieval/runtime does not use it. |
| Context OFF and Context ON both execute | Yes | **PLANNED:** proof/runtime functions are placeholders. |
| Answer trace includes package/rule/approver/source/SQL | Yes | **PLANNED:** response fields exist; QueryService does not populate them. |
| MCP reuses same runtime | Yes | **Structural skeleton only:** MCP helper points at `QueryService`, but no protocol server exists and runtime is placeholder. |

## Layer interaction rules

- Transport code (`rpc/`, `http/`, future MCP) should map requests/responses only. Put business behavior in application/runtime/governance/package services.
- Source registration currently violates the ideal service boundary: RPC/HTTP call `PostgresSourceRepository` directly because no Source application service exists.
- Connectors own provider interaction and read-only verification; they must not own governance or answer reasoning.
- Ingestion owns transformation and persistence/index emission; it currently stops before governance.
- `persistence/` owns CCE state, not business reasoning.
- Traceability and observability are distinct: governance/answer lineage belongs in `traceability/`; diagnostics belong in `observability/`.

## High-impact files — change deliberately

- `backend/proto/cce/v1/*.proto` — public contract; regenerate bindings after changes.
- `backend/src/cce/bootstrap.py` — composition root; changes affect all transports.
- `backend/src/cce/connectors/contracts.py` — connector/change-event contract used across ingestion.
- `backend/src/cce/ingestion/models.py` — canonical data contract consumed across parsers/normalizers.
- `backend/src/cce/ingestion/orchestrator.py` — 500+ line LangGraph workflow; localized changes can alter both lanes.
- `backend/src/cce/persistence/ports.py` and `backend/migrations/cce_control/001_*.sql`/`002_*.sql` — metadata persistence contract/history.
- `backend/src/cce/connectors/structured/snowflake/connector.py` — live source safety boundary.

## Test/build state discovered during this analysis

Do not assume a green repository-wide test run. In the analysis environment, full test collection was blocked by unavailable runtime packages (`langgraph`, `psycopg2`, Azure libraries). A dependency-light subset ran with one concrete failure: `tests/unit/connectors/test_connector_agent.py::RoutingTests::test_structured_registry_kind_routes_to_structured_connect_tool` expects a different skill-trace prefix than the current Snowflake connector emits. `tests/unit/connectors/test_registry_to_structured_connect.py` also contains a stale top-level import that does not match the packaged module path.

The backend Dockerfile is not a reliable proof of the full stack: `deploy/docker/Dockerfile.backend` installs a small hand-written subset and then runs `pip install --no-deps .`, omitting several dependencies declared in `backend/pyproject.toml` that ingestion/connectors/LLM paths require.

## How an agent should explore this repository

1. Read `docs/component-map.yaml` and the nearest module `AGENTS.md` first.
2. Check `docs/IMPLEMENTATION_STATUS.md` before assuming an architecture feature exists.
3. Start from the exact entry point listed for the requested change and follow imports/calls only as needed.
4. For connector or parser work, do not inspect governance/runtime/MCP unless the public contract changes.
5. For governance/package/runtime work, inspect the target documents but label new code as implementing a gap; do not cite placeholder services as precedent for behavior.
6. For API changes, inspect proto + the matching RPC handler + HTTP adapter + application service. Do not fork reasoning logic into a transport.
7. For persistence changes, inspect migration + repository + `persistence/ports.py`; preserve immutable structured snapshots.
8. Do not inspect `frontend/` for backend-only work; it currently contains no application implementation.
9. Treat adapter registry `status="READY"` as metadata, not proof of an executable connector. Verify the factory/provider implementation before using an adapter.
