from fastapi import APIRouter, HTTPException
from api.models import ReviewDecision
from api.store import store

router = APIRouter(prefix="/proposals", tags=["review"])


@router.get("")
def list_proposals(status: str | None = None):
    proposals = store.proposals if not status else [p for p in store.proposals if p["status"] == status]
    return {"proposals": proposals}


@router.get("/{proposal_id}")
def get_proposal(proposal_id: str):
    proposal = next((p for p in store.proposals if p["proposal_id"] == proposal_id), None)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    return proposal


@router.post("/{proposal_id}/approve")
def approve(proposal_id: str, body: ReviewDecision):
    try:
        return store.review(proposal_id, "APPROVED", body.comment)
    except KeyError:
        raise HTTPException(404, "Proposal not found")


@router.post("/{proposal_id}/reject")
def reject(proposal_id: str, body: ReviewDecision):
    try:
        return store.review(proposal_id, "REJECTED", body.comment)
    except KeyError:
        raise HTTPException(404, "Proposal not found")
