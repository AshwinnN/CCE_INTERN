from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.dashboard import router as dashboard_router
from api.routes.ingestion import router as ingestion_router
from api.routes.packages import router as packages_router
from api.routes.query import router as query_router
from api.routes.review import router as review_router

app = FastAPI(title="CCE MVP Frontend Mock API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(packages_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok", "mode": "mock"}
