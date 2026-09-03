# CCE Tool — Governed Context Server

CCE (CoStrategix Context Engine) is packaged as a **server-side tool** that applications, REST clients, MCP clients, and AI agents can plug into. The current working CCE implementation is preserved under `backend/app/`; the reorganization does not change its ingestion/connectors/repository logic.

## Repository layout

```text
CCE-Tool/
├── README.md
├── backend/
│   └── app/
│       ├── api/                    # REST API surface
│       │   ├── routes/              # Health, memory and MVP routes
│       │   ├── schemas/             # API request/response contracts
│       │   └── services/             # API-facing service adapters
│       ├── integrations/             # External SDK/application boundaries
│       ├── mcp/                     # MCP integration boundary / placeholder
│       ├── agent/                   # AI-agent integration boundary / placeholder
│       ├── agents/                  # Existing CCE execution/orchestration code
│       ├── common/                  # Existing shared utilities
│       ├── connectors/              # Existing source connectors
│       ├── ingestion/               # Existing ingest/parsing code
│       ├── repository/              # Existing metadata repository code
│       ├── schema/                  # Existing database schemas
│       ├── prompts/                 # Existing prompts
│       ├── resources/               # MVP/architecture source artifacts
│       │   └── CCE_MVP.pdf
│       ├── tests/                   # Existing tests
│       ├── tools/                   # Existing operational/demo tools
│       ├── .env.example
│       ├── requirements.txt
│       └── docker-compose.yaml
└── frontend/
    ├── public/
    ├── src/
    │   ├── components/
    │   ├── layouts/
    │   ├── pages/
    │   ├── services/
    │   └── types/
    ├── package.json
    └── README.md
```

## Important design boundary

CCE is the server/tool. REST, MCP, and AI-agent clients are access/integration surfaces; they are not the CCE core. Existing CCE functionality remains in `backend/app/` and is not rewritten as part of this packaging change.

### AgenticPlane SDK

The REST memory routes use the existing AgenticPlane SDK contract supplied by the project:

- `plane.memory.store(...)` — StoreLongTerm
- `plane.memory.store_batch(...)` — StoreLongTermBatch
- `plane.memory.search(...)` — SearchLongTerm

The adapter deliberately does not duplicate memory behavior. It resolves an already-created `plane` object and calls those SDK methods directly. The concrete SDK construction can be supplied by the host application through `CCE_AGENTICPLANE_FACTORY` so CCE does not invent or hard-code an SDK constructor that is outside this repository.

## REST API

Run from the repository root:

```powershell
cd backend/app
python -m pip install -r requirements.txt
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Health check:

```text
GET http://localhost:8000/health
```

The MVP-related routes are registered now as a stable API surface and intentionally return `501 Not Implemented` until the corresponding MVP capability is built. This keeps the route contract visible without pretending unfinished functionality is complete.

## Frontend

The frontend is intentionally a **Coming Soon** shell. Its folders establish the production UI boundary without implementing CCE behavior.

```powershell
cd frontend
npm install
npm run dev
```

## Existing CCE implementation

The existing implementation is the source of truth for current behavior. In particular, the Connector Agent, ingestion workflow, connectors, parsers, DLP handling, metadata repository, checkpointing, and tests were moved as-is under `backend/app/`.

The MVP source artifact is `backend/app/resources/CCE_MVP.pdf`. It describes the active context loop, proposed/review/approve lifecycle, domain package, guarded query, compare-and-answer proof, traceability, and MCP serving flow. See page 1 of that artifact for the end-to-end MVP flow.
