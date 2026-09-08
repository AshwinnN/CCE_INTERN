# CCE Frontend Mock API

This is an additive, temporary JSON API for the CCE frontend MVP. It intentionally lives outside `backend/src/cce` so the existing CCE backend implementation is not changed.

The API owns mock UI state only and mirrors the MVP flow:

1. Ingestion -> Ingest & Ground -> Entity Resolution
2. Proposed items -> Human Review / Approve or Reject
3. Approved assets -> Domain Package creation and active version
4. Question workspace -> Context ON/OFF comparison, traceability, and package selection

## Run

From `backend/`:

```powershell
pip install -e .[dev]
uvicorn api.main:app --reload --port 8001
```

Base URL: `http://localhost:8001/api/v1`

## Important boundary

The ingestion endpoint is deliberately shaped as the seam where the future AgenticPlane integration will be connected. In mock mode it returns deterministic AgenticPlane-shaped results for UI development. It does not modify the existing CCE ingestion/runtime implementation.
