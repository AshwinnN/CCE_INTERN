# CCE Tool

CCE (CoStrategix Context Engine) is a governed context server. The backend
owns source registration, ingestion orchestration, governance, context
packages, guarded query runtime boundaries, traceability, and MCP exposure.

## Layout

```text
backend/                  Python gRPC/MCP backend
backend/proto/            Protobuf-first service contracts
backend/src/cce/          CCE application package
backend/skills/           Versioned skill assets
backend/migrations/       cce_control PostgreSQL migrations
backend/tests/            Unit, integration, contract, and e2e tests
frontend/                 Placeholder for future UI
scripts/                  Local generation, migration, and diagnostic scripts
deploy/docker/            Backend container image
docs/                     Architecture, ADRs, and source references
```

## Local Commands

Install the backend in editable mode from `backend/`:

```powershell
pip install -e .[dev]
```

Run tests from `backend/`:

```powershell
python -m pytest
```

Generate protobuf code:

```powershell
python ..\scripts\generate_proto.py
```

Start the gRPC backend:

```powershell
python -m cce.main
```

Local PostgreSQL uses the `cce_control` database. To start the server and
database together, run:

```powershell
docker compose up --build
```

Smoke-check the gRPC health endpoint:

```powershell
docker compose exec backend python /app/scripts/smoke_server.py --target localhost:50051
```

## Architecture

The target repository structure is tracked at
`docs/architecture/structure.md`. AgenticPlane remains behind
`backend/src/cce/integrations/agentic_plane/`; CCE does not own graph,
vector, embedding, chunking, or retrieval infrastructure.
