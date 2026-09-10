# CoStrategix Context Engine

CCE ingests source evidence, stages machine proposals, requires human review, builds an immutable Workspace context package and answers through parallel Context ON/OFF branches. PostgreSQL owns governed state. AgenticPlane supplies candidate vector evidence; only the active package version's assets govern Context ON.

Workspace is the single top-level governance/runtime scope: `Workspace -> Sources -> exactly one Context Package (v1, v2, v3, ...)`. There is no Domain concept, no domain selection and no domain-routing LLM; a query always executes directly at Workspace scope.

## Layout

- `backend/src/cce/`: real services, Workspace-scoped source/query/SQL LangGraphs (including multi-question atomization in `runtime/compound.py`), PostgreSQL repositories and transport adapters.
- `backend/proto/`: gRPC contracts (`common.proto`, `health.proto`, `workspaces.proto`); regenerate with `python scripts/generate_proto.py`.
- `backend/migrations/cce_control/`: forward migrations, including `012_domain_governance_lifecycle.sql`, `013_runtime_and_jobs.sql` and `014_workspace_scope.sql` (the Domain-to-Workspace migration; see `docs/decisions/ADR-005-workspace-replaces-domain.md`).
- `backend/tests/`: unit, lifecycle integration and explicitly enabled live tests.
- `frontend/`: the Workspace-scoped production UI (`/workspaces`, `/workspaces/:workspaceId/{sources,proposals,package,query}`).

## Development

Install from `backend/` with `pip install -e '.[dev]'`. AgenticPlane >=1.3 requires the organization's private Python registry; supply authentication outside the repository. Copy `.env.example` and configure PostgreSQL, index and model providers. Do not commit credentials.

From `backend/`, run `python -m cce.main`. Startup applies migrations, starts the durable ingestion job worker, and serves gRPC (50051) plus HTTP (8080 by default). PostgreSQL is required (with pgvector, for feedback memory and local vector indexing). AgenticPlane mode does not require local pgvector indexing, but feedback memory always uses PostgreSQL+pgvector.

Create a Workspace through `POST /workspaces` with an ADMIN actor (`workspace_id` is derived as `{name}_workspace` and is immutable; a package row is created automatically, with no `v1` until the first approved proposal batch). Register/test sources under `/workspaces/{workspace_id}/sources` (discover schemas first via `/workspaces/{workspace_id}/sources/discover`), then explicitly trigger `/workspaces/{workspace_id}/sources/{source_uuid}/ingest` and poll `/workspaces/{workspace_id}/ingestion-runs/{run_uuid}`. Review/edit all proposals and approve/reject them with a STEWARD actor; once every proposal in a batch is terminal, an approved change builds the next package version. Query with `POST /workspaces/{workspace_id}/query`; a Workspace with no active approved package version rejects the query with a structured `NO_ACTIVE_PACKAGE` error rather than silently answering Context-OFF-only.

Deploy the adapters behind authenticated infrastructure that supplies trustworthy actor claims. The application role fields alone are not authentication. `/workspaces/{workspace_id}/retrieve` is raw infrastructure diagnostics, not a governed query endpoint, and is Workspace-scoped like every other route.

## Tests

Run non-live unit tests from `backend/`:

```sh
PYTHON_DOTENV_DISABLED=1 python -m pytest tests/unit
```

Lifecycle tests create/drop uniquely named databases on a disposable PostgreSQL server. The configured test user needs CREATE DATABASE permission; application databases are not truncated.

```sh
PYTHON_DOTENV_DISABLED=1 CCE_TEST_DATABASE_URL='postgresql://test_user:test_password@localhost/postgres' python -m pytest tests/integration/lifecycle
```

Live Azure/Snowflake tests require explicit live-test flags and credentials. Fixture tests do not establish hosted accuracy/lift.

See [implementation status](docs/IMPLEMENTATION_STATUS.md), [implementation report](docs/IMPLEMENTATION_REPORT.md), and the [architecture](docs/architecture/structure.md).

## Typed source connectors

`GET /source-types` provides configuration schemas for Snowflake, PostgreSQL,
SQL Server, MySQL, Azure Blob and Google Drive -- the only six production READY
source types; `local-fs` remains available internally for tests/development but
is not returned by this catalog. See `docs/IMPLEMENTATION_REPORT.md` for exact
wiring, dependencies and outstanding work. SQL Server requires ODBC Driver 18;
Google Drive uses service-account credentials and an explicit folder/drive.
