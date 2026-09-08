# Governed lifecycle implementation report

## Implemented behavior

Real backend services now connect durable source ingestion to staged extraction, steward review, full domain-package snapshots, package-filtered evidence retrieval, parallel Context ON/OFF answering, guarded SQL with repair, and durable traces. `backend/api/` remains a development mock and does not own these behaviors.

The final decision in a batch triggers deterministic validation and atomic activation. Partial ingestion cannot expose proposals. Rejected, no-change and structurally blocked batches do not increment versions. Approved removals retire assets only after successful package creation and preserve historical versions.

Expired job claims cannot finalize runs; indexed document identities also include the claim token to isolate stale workers. SQL scope validation respects quoted identifier casing.

## Important files

| Responsibility | Files under `backend/src/cce/` |
|---|---|
| Composition/configuration | `bootstrap.py`, `main.py`, `config/settings.py` |
| Source workflow | `ingestion/source_graph.py`, `ingestion/grounding.py`, `ingestion/lifecycle_models.py`, `ingestion/job_runner.py`, `sources/service.py`, `sources/models.py` |
| Models/review | `context_packages/models/assets.py`, `governance/models.py`, `governance/service.py`, `governance/state_machine.py` |
| Package lifecycle | `context_packages/builder.py`, `context_packages/validator.py`, `context_packages/service.py` |
| Governed state | `persistence/postgres/{lifecycle_db,domain_repository,ingestion_repository,job_repository,governance_repository,context_repository,runtime_repository}.py` |
| Query/SQL | `runtime/models.py`, `runtime/orchestrator.py`, `runtime/service.py`, `runtime/sql_pipeline.py`, `runtime/sql_guard.py`, `runtime/sql_executor.py` |
| External boundaries | `integrations/llm/client.py`, `integrations/agentic_plane/client.py`, `integrations/agentic_plane/local_index.py`, `connectors/structured/snowflake/connector.py` |
| Transports | `http/app.py`, `rpc/services/{domain,governance,package,query,source}_service.py`, `rpc/services/errors.py`, `rpc/server.py`, `mcp/tools/query.py` |
| DLP | `security/dlp.py` |

Protobuf changes: `backend/proto/cce/v1/{domains,governance,packages,query}.proto`. Python bindings were regenerated using `scripts/generate_proto.py`; generated files follow the repository's existing ignore policy and must be regenerated in a clean checkout/build.

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

HTTP adds `POST/GET /domains`, proposal PATCH and filters, and `GET /packages/{domain_id}/active`. Existing source routes now return durable run state in production. `/query` accepts optional `domain_id` and returns domain/package resolution, ON/OFF branches and proof. Governance/package routes use real repositories.

gRPC adds DomainService, EditProposal, GetActivePackage, proposal filters and typed branch/proof messages with Struct fields for dynamic payloads, evidence, SQL rows and attempts. All adapters share services. The MCP Python helper accepts domain/actor parameters and delegates to QueryService.

Source graph nodes: `discover_and_diff_inventory`, `process_item` via Send, `aggregate_item_results`, `promote_staged_candidates`. Item processing includes grounding, domain detection, scoped indexing/search and one typed extraction per item/domain.

Query graph nodes: `create_trace`, `parse_question`, `resolve_domain`, `load_active_package`, parallel `context_on_subgraph`/`context_off_subgraph`, `proof_classifier`, `persist_trace_finalizer`.

Branch nodes: `retrieve_and_assemble`, `resolve_data_source`, `run_sql_subgraph`, `answer`. SQL nodes: `generate_sql`, `parse_sql`, `validate_sql`, `guard_sql`, `execute_sql`, `describe_sql_error`, `persist_attempt`.

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
