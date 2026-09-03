"""CCE Tool REST server.

This module is intentionally a thin HTTP boundary around the existing CCE
implementation. It does not replace or rewrite the current ingestion logic.
"""
from fastapi import FastAPI

from api.routes.health import router as health_router
from api.routes.memory import router as memory_router
from api.routes.mvp import router as mvp_router

app = FastAPI(
    title="CCE Tool",
    version="0.1.0",
    description="Governed Context Engine server boundary for applications, MCP clients and AI agents.",
)

app.include_router(health_router)
app.include_router(memory_router, prefix="/api/v1")
app.include_router(mvp_router, prefix="/api/v1")


@app.get("/", tags=["system"])
def root():
    return {
        "service": "cce-tool",
        "status": "ok",
        "message": "CCE Tool server is running",
        "health": "/health",
        "api_prefix": "/api/v1",
    }
