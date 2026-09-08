from fastapi import APIRouter
from api.models import IngestRequest
from api.store import store

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/runs")
def list_runs():
    return {"runs": store.ingestion_runs}


@router.post("/run")
def run_ingestion(body: IngestRequest):
    return store.ingest(body.document_name, body.source)
