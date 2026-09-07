from fastapi import APIRouter
from api.store import store

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary():
    return {
        "ingestion_runs": len(store.ingestion_runs),
        "proposed": sum(p["status"] == "PROPOSED" for p in store.proposals),
        "approved": sum(p["status"] == "APPROVED" for p in store.proposals),
        "active_packages": sum(p["status"] == "ACTIVE" for p in store.packages),
    }
