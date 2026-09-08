# CoStrategix Context Engine

CCE ingests source evidence, stages machine proposals, requires human review, builds immutable domain packages and answers through parallel Context ON/OFF branches. PostgreSQL owns governed state. AgenticPlane supplies candidate vector evidence; only active package assets govern Context ON.

## Layout

- `backend/src/cce/`: real services, source/query/SQL LangGraphs, PostgreSQL repositories and transport adapters.
- `backend/proto/`: gRPC contracts; regenerate with `python scripts/generate_proto.py`.
- `backend/migrations/cce_control/`: forward migrations, including `012_domain_governance_lifecycle.sql` and `013_runtime_and_jobs.sql`.
- `backend/tests/`: unit, lifecycle integration and explicitly enabled live tests.
- `frontend/` and `backend/api/`: development UI and mock API, separate from the production backend.

## Development

Install from `backend/` with `pip install -e '.[dev]'`. AgenticPlane >=1.3 requires the organization's private Python registry; supply authentication outside the repository. Copy `.env.example` and configure PostgreSQL, index and model providers. Do not commit credentials.

From `backend/`, run `python -m cce.main`. Startup applies migrations, starts the durable ingestion job worker, and serves gRPC (50051) plus HTTP (8080 by default). PostgreSQL is required. Local vector indexing additionally requires pgvector; AgenticPlane mode does not.

Create domains through `POST /domains` with an ADMIN actor. Register/test sources, then explicitly trigger `/sources/{source_id}/ingest` and poll `/ingestion-runs/{run_id}`. Review/edit all proposals and approve/reject them with a STEWARD actor. The last decision automatically builds the domain package. Query with `POST /query` and an optional `domain_id`.

Deploy the adapters behind authenticated infrastructure that supplies trustworthy actor claims. The application role fields alone are not authentication. `/retrieve` is raw infrastructure diagnostics, not a governed query endpoint.

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
