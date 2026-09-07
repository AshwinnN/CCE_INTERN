# CCE Implementation Status

## Executive summary

This file answers: **what does this repository actually support today?**

The supplied capability-mapping document labels itself **"63 TOTAL CAPABILITIES"**, but its explicit ID rows enumerate **76 capabilities** (SF 8 + DOC 9 + ER 7 + CTX 10 + GOV 10 + PKG 9 + RT 11 + TRACE 7 + MCP 5). This cross-check uses the 76 explicit capability IDs rather than silently forcing the inconsistent header count.

Capability classification across those 76 rows:

| Status | Count |
|---|---:|
| IMPLEMENTED | 4 |
| PARTIAL | 16 |
| PLANNED | 56 |
| LEGACY / UNUSED | 0 |
| UNKNOWN / REQUIRES VERIFICATION | 0 |

`IMPLEMENTED` means the behavior is present on a real executable component/workflow path, not merely represented by a class or contract.

## Fully Implemented

### Snowflake connection and read-only verification — SF-01

Status: **IMPLEMENTED**

Evidence:
- `backend/src/cce/connectors/structured/snowflake/connector.py::SnowflakeConnector.connect()`
- `_run_write_probe()` performs `CREATE TEMPORARY TABLE` and rejects a credential if the write succeeds.
- `ConnectorFactory` registers the Snowflake connector.

### Snowflake schema discovery — SF-02

Status: **IMPLEMENTED**

Evidence:
- `SnowflakeConnector.get_information_schema_card()`
- `SnowflakeConnector.get_schema_card()`
- `connectors/fetch.py::snowflake_schema_fetcher()` is the production structured fetch default used by ingestion.

### One sample record per Snowflake table — SF-03

Status: **IMPLEMENTED**

Evidence:
- `SnowflakeConnector.get_schema_card()` runs `SELECT * ... LIMIT 1` per readable table.
- `snowflake_schema_fetcher()` calls `get_schema_card()`.

Boundary: sample rows are not persisted in `PostgreSQLMetadataRepository`; retrieval from CCE storage is therefore a separate partial capability (SF-06).

### Structured Snowflake metadata persistence — SF-04

Status: **IMPLEMENTED**

Evidence:
- `ingestion/orchestrator.py::persist_structured_metadata_node()`
- `persistence/postgres/metadata_repository.py::PostgreSQLMetadataRepository`
- migrations `001_registry.sql`, `002_metadata.sql`, `002_metadata_01_details.sql`, `002_metadata_02_relationships.sql`.

## Partially Implemented

### Stored schema retrieval — SF-05

Status: **PARTIAL**

Implemented:
- `PostgreSQLMetadataRepository.list_tables()` and `list_columns()` retrieve snapshot metadata.

Missing:
- no active public service/runtime path exposes stored-schema retrieval as a product capability.

### Stored sample-record retrieval — SF-06

Status: **PARTIAL**

Implemented:
- sample row is collected from Snowflake by `get_schema_card()` and can exist in the normalized/emitted payload.

Missing:
- metadata persistence schema/repository does not store sample rows; no retrieval method exists.

### Approved/verified query execution — SF-08

Status: **PARTIAL**

Implemented:
- `SnowflakeConnector.execute_query()` executes parameterized DB-API calls.
- Snowflake connection itself is rejected when write access is detected.

Missing:
- no approved/verified SQL library integration;
- runtime `sql_executor` is unimplemented;
- `sql_guard` is not wired;
- no runtime row cap/statement timeout.

### Document source connection — DOC-01

Status: **PARTIAL**

Implemented:
- provider-neutral unstructured contracts/agent path;
- real Azure Blob SDK code in `connectors/unstructured/azure_blob/connector.py` and `connectors/fetch.py::azure_blob_fetcher()`;
- executable `local-fs` connector for synthetic/demo ingestion;
- server `TestConnection` composes registered source config through `cce.sources.service.SourceService`.

Missing:
- production provider breadth remains limited to Snowflake and Azure Blob plus local demo files;
- auth/authz is not enforced before source administration.

### Document discovery — DOC-02

Status: **PARTIAL**

Implemented:
- `AzureBlobSource.process_blobs()` lists blobs;
- `AzureBlobSource.list_objects()` and `LocalFileSystemConnector.list_objects()` support server-triggered ingestion;
- `UnstructuredChangeObserver` handles an object-lister result and emits change events.

Missing:
- no scheduling or continuous provider polling loop;
- registry READY status is broader than executable factory/provider support.

### Document content ingestion — DOC-03

Status: **PARTIAL**

Implemented:
- real fetch, parser selection, canonical normalization, SDK-emission hook and file checkpoint in `ingestion/orchestrator.py`;
- MIME-based parsing uses text/csv/excel parsers, `pypdfium2` for PDFs, `python-docx` for Word files and `python-pptx` for PowerPoint files;
- server `TriggerIngestion` creates an ingestion run, calls the real workflow and updates durable run state;
- the configured AgenticPlane boundary can be the SDK-backed `AgenticPlaneClient`
  for hosted writes or the pgvector-backed `LocalIndexClient` fallback;
- the hosted path sends raw chunks to `memory.store_batch()`, persists returned
  IDs in `cce_agentic_plane_memory`, synchronously extracts graph data per
  memory, and supports document replacement/deletion;
- the separate raw `POST /retrieve` and `RetrievalService.Retrieve` surfaces
  return direct memory-search and GraphRAG records with a request trace ID.

Missing:
- no governance proposal output.
- the governed `/query` runtime read/context-assembly path is not wired; raw
  retrieval does not provide governance, packages or answer synthesis.

### Raw AgenticPlane graph proof — DOC-06, DOC-07, DOC-08

Status: **PARTIAL** at product capability level; executable for raw hosted
retrieval when AgenticPlane graph services are enabled.

Implemented:
- ingestion calls synchronous `graph.extract_and_store()` once per stored
  memory and reports entity/relationship response counts;
- `AgenticPlaneClient.graph()` maps `graphrag_search()` results without
  synthesis;
- `/retrieve` and the equivalent gRPC RPC return memory and graph records with
  traceable source metadata;
- local fallback returns memory results plus an explicit graph-unsupported
  marker.

Boundary:
- AgenticPlane must run with `GRAPH_ENABLED=true` and ArcadeDB available;
- this is not entity resolution, governed context, package construction or the
  governed `/query` runtime.

### Server source lifecycle

Status: **PARTIAL**

Implemented:
- gRPC and HTTP source endpoints delegate to `cce.sources.service.SourceService`;
- `RegisterSource` persists source kind, credential reference and non-secret config;
- `GetIngestionStatus` reads durable run state from PostgreSQL.

Missing:
- no source scheduling/continuous change capture service;
- no source-admin auth/authz enforcement.

### Changed-document reprocessing — DOC-04

Status: **PARTIAL**

Implemented:
- change-event/idempotency logic and `UnstructuredChangeObserver`/`StructuredChangeObserver` exist;
- ingestion has file-backed processing checkpoints.

Missing:
- observation checkpoint/dedup stores default to in-memory;
- live provider listing/change-feed wiring is injected rather than composed in the server.

### Fact provenance — DOC-09

Status: **PARTIAL**

Implemented:
- source/object/version information is retained in change events and canonical document metadata.

Missing:
- no fact extraction capability exists, so there is no fact-level provenance model/path;
- answer-level lineage is not implemented.

### Prevent unapproved rules from being used — GOV-10

Status: **PARTIAL**

Implemented:
- `governance/policy.py::require_approved()`
- `context_packages/builder.py::assert_assets_approved()`

Missing:
- governance/package/runtime are not implemented, so no mandatory runtime retrieval boundary calls these checks.

### Domain package versioning — PKG-08

Status: **PARTIAL**

Implemented:
- `context_packages/versioning.py::next_patch_version()`.

Missing:
- no persisted package/version store, immutable package builder, active version selection, or approval-driven version bump.

### Live query execution in runtime — RT-08

Status: **PARTIAL**

Implemented:
- low-level Snowflake `execute_query()` exists.

Missing:
- `runtime/sql_executor.py::execute_read_only()` raises `NotImplementedError`;
- no orchestrator path invokes guarded live execution.

### Answer trace ID — TRACE-01

Status: **PARTIAL**

Implemented:
- connector flow creates trace IDs in `rpc/interceptors/correlation.py::new_trace_id()`/connector code paths.

Missing:
- `QueryService` does not generate an answer trace ID; it only echoes optional metadata.

### MCP accepts an external question — MCP-01

Status: **PARTIAL**

Implemented:
- a Python helper `mcp/tools/query.py::query()` can call `QueryService`.

Missing:
- no MCP protocol server/listener/tool registration exists; `create_mcp_server()` returns a dict.

## Planned / Not Yet Implemented

The following capability IDs have no meaningful active implementation beyond contracts, dataclasses, skills, TODO/stub functions, or architecture material:

- **SF-07** Generate a candidate data query from stored schema.
- **DOC-05** Extract traceable facts from a document.
- **ER-01..ER-07** question/graph/Snowflake entity identification and resolution, ambiguity/unresolved handling.
- **CTX-01..CTX-10** business concept/definition/value/policy extraction, linkage, semantic mapping, query mapping, verified SQL generation.
- **GOV-01..GOV-09** proposal creation, display/evidence/provenance, approve/reject, approver/timestamp/validity persistence.
- **PKG-01..PKG-07, PKG-09** package creation/assets/graph/ambiguity and rule-to-version association.
- **RT-01..RT-07, RT-09..RT-11** question parsing, graph/rule/entity/live-data/SQL resolution, rule application, answer generation and explanation.
- **TRACE-02..TRACE-07** rule version, approver, validity, source provenance, complete context-used trace, explanation.
- **MCP-02..MCP-05** governed runtime resolution, business-context resolution, live-data retrieval through MCP, governed MCP answer.

## Full capability-to-code cross-check

| Capability | Status | Evidence / active path | Known gap |
|---|---|---|---|
| SF-01 Connect to Snowflake | IMPLEMENTED | `SnowflakeConnector.connect()` via factory/ingestion | — |
| SF-02 Discover database structure | IMPLEMENTED | `get_information_schema_card()`, `get_schema_card()` | — |
| SF-03 Capture one sample record per table | IMPLEMENTED | `get_schema_card()` → `LIMIT 1`; production fetcher calls it | Not persisted |
| SF-04 Store Snowflake metadata | IMPLEMENTED | `persist_structured_metadata_node()` → `PostgreSQLMetadataRepository`; server source trigger calls this workflow | No sample-row persistence |
| SF-05 Retrieve stored schema | PARTIAL | repository `list_tables/list_columns` | No active product API/runtime consumer |
| SF-06 Retrieve stored sample records | PARTIAL | sample exists in fetched card | No sample persistence/retrieval contract |
| SF-07 Generate candidate data query | PLANNED | `runtime/sql_generator.py` stub; SQL skill asset | No active generator |
| SF-08 Execute approved/verified query | PARTIAL | `SnowflakeConnector.execute_query()` | Not tied to approval/verified SQL/guard |
| DOC-01 Connect to document source | PARTIAL | Azure Blob and local-fs SourceConnector paths plus source service TestConnection | Limited provider breadth; no source-admin auth |
| DOC-02 Discover documents | PARTIAL | Azure Blob/local-fs listing; observer accepts lister | no scheduler/continuous change feed |
| DOC-03 Ingest document content | PARTIAL | source service trigger -> `run_ingestion()` -> configured index boundary | no governance proposal output |
| DOC-04 Re-process changed documents | PARTIAL | change observers + idempotency | observer state in memory; provider wiring injected |
| DOC-05 Extract traceable facts | PLANNED | no active implementation | — |
| DOC-06 Identify entities in content | PARTIAL | hosted ingestion synchronously calls AgenticPlane extraction per memory | external extraction only; no governed proposal/entity-resolution flow |
| DOC-07 Identify relationships | PARTIAL | AgenticPlane extraction returns stored relationships | external extraction only; no governed fact-linking flow |
| DOC-08 Build/update knowledge graph | PARTIAL | SDK graph write and raw GraphRAG retrieval are active behind the boundary | requires hosted graph services; local backend has no graph |
| DOC-09 Preserve fact provenance | PARTIAL | document/change-event provenance | facts not extracted; answer lineage absent |
| ER-01 Identify entities in question | PLANNED | `runtime/entity_resolution.py` returns `[]` | — |
| ER-02 Candidate graph entities | PLANNED | no active graph retrieval | — |
| ER-03 Candidate Snowflake entities | PLANNED | no active entity candidate resolver | — |
| ER-04 Resolve document/graph to Snowflake | PLANNED | entity-resolution skill only | — |
| ER-05 Resolve entity attributes/keys | PLANNED | no active implementation | — |
| ER-06 Detect ambiguous entity resolution | PLANNED | no active implementation | — |
| ER-07 Handle unresolved entity resolution | PLANNED | no active implementation | — |
| CTX-01 Extract business concepts | PLANNED | skill/reference assets only | no production skill execution |
| CTX-02 Extract business definitions | PLANNED | skill/reference assets only | no production skill execution |
| CTX-03 Extract business values | PLANNED | no active implementation | — |
| CTX-04 Extract policy conditions | PLANNED | policy skill/reference only | no active extraction |
| CTX-05 Extract policy rules | PLANNED | policy skill/reference only | no active extraction |
| CTX-06 Extract rule validity | PLANNED | target proto fields only | no active extraction |
| CTX-07 Link facts to entities | PLANNED | no active implementation | — |
| CTX-08 Link business to Snowflake concepts | PLANNED | semantic mapping skill only | no active mapper |
| CTX-09 Generate query mapping | PLANNED | no active implementation | — |
| CTX-10 Generate verified SQL | PLANNED | `runtime/sql_generator.py` raises | verified SQL model is data-only |
| GOV-01 Create proposed rule | PLANNED | governance service placeholder | ingestion never creates proposal |
| GOV-02 Show proposed rule | PLANNED | RPC/proto mapping exists | service returns empty/NOT_FOUND |
| GOV-03 Show rule provenance | PLANNED | proto can carry evidence | no persisted proposal |
| GOV-04 Show supporting evidence | PLANNED | proto can carry evidence | no persisted proposal |
| GOV-05 Approve rule | PLANNED | RPC method delegates | service returns NOT_FOUND |
| GOV-06 Reject rule | PLANNED | RPC method delegates | service returns NOT_FOUND |
| GOV-07 Record approver | PLANNED | proto field exists | no persistence |
| GOV-08 Record approval timestamp | PLANNED | proto field exists | no persistence |
| GOV-09 Record rule validity | PLANNED | proto field exists | no persistence |
| GOV-10 Prevent unapproved use | PARTIAL | `require_approved()`, `assert_assets_approved()` | no active governed serving path |
| PKG-01 Create Domain Package | PLANNED | package model/service placeholder | no builder/persistence |
| PKG-02 Add glossary entries | PLANNED | `GlossaryTerm` dataclass | no package store |
| PKG-03 Add semantic mappings | PLANNED | `SemanticMapping` dataclass | no package store |
| PKG-04 Add policy rules | PLANNED | `PolicyRule` dataclass | no package store |
| PKG-05 Add verified SQL | PLANNED | `VerifiedSQL` dataclass | no package store |
| PKG-06 Add entity graph info | PLANNED | target architecture only | no graph/package integration |
| PKG-07 Maintain ambiguity info | PLANNED | `Ambiguity` dataclass | no package store/resolver |
| PKG-08 Version Domain Package | PARTIAL | `next_patch_version()` | no persisted immutable versions |
| PKG-09 Associate rules with versions | PLANNED | proto assets field only | no storage |
| RT-01 Parse business question | PLANNED | `determine_intent()` returns `unknown` | — |
| RT-02 Retrieve graph facts | PLANNED | AgenticPlane vector search exists only at the integration boundary | no active governed runtime retrieval or graph-fact path |
| RT-03 Identify applicable rule | PLANNED | `resolve_rules()` returns `[]` | — |
| RT-04 Validate applicability | PLANNED | no active implementation | — |
| RT-05 Resolve Snowflake entity | PLANNED | entity resolver returns `[]` | — |
| RT-06 Determine live data required | PLANNED | `requires_live_data()` returns `False` | — |
| RT-07 Generate/retrieve required SQL | PLANNED | generator raises; no verified library lookup | — |
| RT-08 Execute live query | PARTIAL | Snowflake low-level executor exists | runtime executor raises; no guard wiring |
| RT-09 Apply business rule | PLANNED | no active implementation | — |
| RT-10 Produce business answer | PLANNED | QueryService fixed not-implemented text | — |
| RT-11 Explain applied context | PLANNED | response fields exist | no context reasoning |
| TRACE-01 Generate answer trace ID | PARTIAL | trace IDs in connector path | QueryService does not generate one |
| TRACE-02 Attach rule version | PLANNED | query proto fields can carry data | not populated |
| TRACE-03 Attach approver | PLANNED | query proto field | not populated |
| TRACE-04 Attach rule validity | PLANNED | query proto field | not populated |
| TRACE-05 Attach source provenance | PLANNED | query citations contract | no answer lineage construction |
| TRACE-06 Identify all context used | PLANNED | `context_used` field | no runtime context |
| TRACE-07 Explain why context selected | PLANNED | no active implementation | — |
| MCP-01 Accept external-agent question | PARTIAL | Python `mcp.tools.query()` helper | no MCP protocol server |
| MCP-02 Execute CCE runtime resolution | PLANNED | helper delegates to placeholder QueryService | — |
| MCP-03 Resolve applicable context | PLANNED | runtime missing | — |
| MCP-04 Retrieve live data when required | PLANNED | runtime missing | — |
| MCP-05 Return governed answer | PLANNED | runtime returns not-implemented answer | — |

## Other major product invariants

| Product invariant | Status | Evidence / gap |
|---|---|---|
| Domain-blind core | PARTIAL | No hardcoded business-domain terms found in `backend/src`; no automated guard/test enforces this. |
| Human approval boundary | PLANNED | Governance service and persistence absent. |
| Approved-only runtime context | PARTIAL | helper functions exist; no live runtime boundary calls them. |
| Read-only source connectors | PARTIAL | Snowflake proven; unstructured/provider breadth largely declarative/injected. |
| SELECT-only execution | PARTIAL | simple prefix guard exists; not called in live query method. |
| Statement timeout / row limit | PLANNED in runtime | settings exist but execution does not enforce them. |
| Structured ingestion | PARTIAL at product level | real workflow exists and server trigger is wired for Snowflake schema ingest; no downstream governance proposal. |
| Unstructured ingestion | PARTIAL | parsing/fetching works and source trigger can index local-fs/Azure Blob content; no governance proposal. |
| Active changed-document loop | PARTIAL | event logic exists; durable/provider wiring incomplete; no package delta/version loop. |
| Entity extraction/resolution | PARTIAL | raw hosted AgenticPlane extraction/GraphRAG works; governed entity resolution remains unbuilt. |
| Semantic/policy extraction | PLANNED | skills/placeholders only. |
| Verified SQL generation/storage | PLANNED | model/skill only. |
| Package construction/version persistence | PLANNED | helper-only partial version increment. |
| Ambiguity register | PLANNED | dataclass only. |
| Context OFF | PLANNED | no baseline executor. |
| Context ON | PLANNED | no governed context executor. |
| OFF vs ON comparison | PLANNED | proof function returns `{}`. |
| Answer traceability | PLANNED | contracts exist, no builder/persistence. |
| API boundary | PARTIAL | gRPC/HTTP source operations and raw retrieval are wired; governance/package/query remain placeholders; no auth. |
| MCP boundary | PLANNED | no protocol server. |
| Workflow/service/repository separation | PARTIAL | source RPC/HTTP share SourceService; governance/package/runtime remain placeholder services. |

## Legacy / Suspected Unused

No **major capability** is classified `LEGACY / UNUSED`. The repository does contain disconnected/overlapping code paths listed below, but that evidence is not sufficient to declare their intended functionality obsolete.

## Unknown / Requires Verification

No capability in the supplied mapping required `UNKNOWN / REQUIRES VERIFICATION` after code tracing. The repository now contains a real AgenticPlane SDK adapter, while live hosted persistence remains an integration-environment behavior verified by the guarded smoke script rather than claimed from source inspection alone.

## Potential dead / duplicate / disconnected code with concrete evidence

These are **not** automatically safe to delete; they are areas where call-site evidence shows disconnection or overlap.

- `backend/src/cce/connectors/unstructured/azure_blob/connector.py::AzureBlobSource` and `connectors/fetch.py::azure_blob_fetcher()` — both remain; the source service now uses the SourceConnector path.
- `backend/src/cce/skills/loader.py` — current call sites found only in tests; no production module loads a skill.
- `backend/proto/cce/v1/query.proto::ContextComparison` — message is defined but no RPC request/response field references it.
- `backend/src/cce/persistence/postgres/checkpoint_repository.py::PostgresCheckpointRepository` — method body raises `NotImplementedError`; no call sites found.

## Verification notes

- The repository registry advertises more adapters as `READY` than have executable implementations. Treat factory/provider code, not registry metadata, as support evidence.
- `frontend/` contains no implementation beyond a README.
- Full non-live backend tests should run with live dotenv settings disabled; live Postgres tests require a reachable `cce_control` database.
