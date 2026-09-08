# CCE MVP Frontend

A React/Vite reference UI for the CCE MVP flow. The frontend consumes only JSON APIs and does not access CCE storage directly.

## Pages

- **Ingestion** — start a mock ingestion run and show Ingest → Ground → Entity Resolution.
- **Review** — list proposed context assets, inspect evidence, approve/reject.
- **Domain Packages** — list packages, create a package from approved proposals, select the active package.
- **Ask Questions** — ask against the selected active package and compare Context OFF vs Context ON with traceability.

## Run

Terminal 1:

```powershell
cd backend
uvicorn api.main:app --reload --port 8001
```

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.
