from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check():
    """Simple liveness check for the CCE Tool server."""
    return {
        "status": "healthy",
        "service": "cce-tool",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
