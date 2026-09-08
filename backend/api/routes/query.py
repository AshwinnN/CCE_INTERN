from fastapi import APIRouter, HTTPException
from api.models import QuestionRequest
from api.store import store

router = APIRouter(prefix="/questions", tags=["questions"])


@router.post("/ask")
def ask(body: QuestionRequest):
    try:
        return store.answer(body.question, body.package_id, body.context_enabled)
    except KeyError:
        raise HTTPException(404, "Active package not found")


@router.post("/compare")
def compare(body: QuestionRequest):
    try:
        off = store.answer(body.question, body.package_id, False)
        on = store.answer(body.question, body.package_id, True)
        return {"question": body.question, "context_off": off, "context_on": on}
    except KeyError:
        raise HTTPException(404, "Active package not found")
