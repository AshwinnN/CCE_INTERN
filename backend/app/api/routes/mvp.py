"""MVP REST route registry.

The CCE MVP PDF is the contract for these capabilities. Routes are registered
now so clients can integrate against stable resource names while implementation
is still in progress. Unimplemented routes fail explicitly with HTTP 501.
"""
from fastapi import APIRouter, HTTPException

from api.schemas.mvp import ApprovalRequest, PlaceholderRequest, QueryRequest

router = APIRouter()


def _not_implemented(capability: str):
    raise HTTPException(
        status_code=501,
        detail={
            "status": "not_implemented",
            "capability": capability,
            "message": "MVP route is reserved; implementation is not complete yet.",
        },
    )


@router.post("/ingestion/events", tags=["mvp - ingest & ground"])
def ingest_event(request: PlaceholderRequest):
    _not_implemented("ingest & ground")


@router.post("/context/resolve", tags=["mvp - context"])
def resolve_context(request: PlaceholderRequest):
    _not_implemented("entity resolution / context grounding")


@router.post("/context/assemble", tags=["mvp - context"])
def assemble_context(request: QueryRequest):
    _not_implemented("governed context assembly")


@router.post("/reviews/{proposal_id}/approve", tags=["mvp - review"])
def approve_proposal(proposal_id: str, request: ApprovalRequest):
    _not_implemented("human review & approve")


@router.post("/reviews/{proposal_id}/reject", tags=["mvp - review"])
def reject_proposal(proposal_id: str, request: ApprovalRequest):
    _not_implemented("human review & reject")


@router.get("/domain-packages/{package_id}", tags=["mvp - domain package"])
def get_domain_package(package_id: str):
    _not_implemented("domain package")


@router.post("/query", tags=["mvp - query"])
def governed_query(request: QueryRequest):
    _not_implemented("governed query runtime")


@router.post("/query/compare", tags=["mvp - proof"])
def compare_answer(request: QueryRequest):
    _not_implemented("compare & answer proof")


@router.get("/traces/{trace_id}", tags=["mvp - observability"])
def get_trace(trace_id: str):
    _not_implemented("traceability & observability")


@router.get("/mcp/manifest", tags=["mvp - mcp"])
def mcp_manifest():
    _not_implemented("MCP serving")
