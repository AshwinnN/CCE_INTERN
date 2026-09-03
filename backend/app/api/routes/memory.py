from fastapi import APIRouter, HTTPException

from api.schemas.memory import MemorySearchRequest, MemoryStoreBatchRequest, MemoryStoreRequest
from api.services.memory_service import MemoryService
from integrations.agenticplane import AgenticPlaneUnavailable

router = APIRouter(prefix="/memory", tags=["memory"])
_service = MemoryService()


def _execute(operation):
    try:
        return {"status": "ok", "result": operation()}
    except AgenticPlaneUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AgenticPlane operation failed: {exc}") from exc


@router.post("/store")
def store(request: MemoryStoreRequest):
    return _execute(lambda: _service.store(request.model_dump(exclude_none=True)))


@router.post("/store-batch")
def store_batch(request: MemoryStoreBatchRequest):
    return _execute(lambda: _service.store_batch(request.model_dump()))


@router.post("/search")
def search(request: MemorySearchRequest):
    return _execute(lambda: _service.search(request.model_dump(exclude_none=True)))
