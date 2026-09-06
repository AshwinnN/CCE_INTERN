"""FastAPI adapter over the same services used by gRPC and MCP."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from cce.runtime.service import QueryRequest


class ActorModel(BaseModel):
    actor_id: str = ""
    roles: list[str] = Field(default_factory=list)


class RegisterSourceBody(BaseModel):
    adapter: str
    source_id: str
    credential_ref: str = ""
    kind: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    actor: ActorModel = Field(default_factory=ActorModel)


class ActorBody(BaseModel):
    actor: ActorModel = Field(default_factory=ActorModel)


class QueryBody(BaseModel):
    question: str
    actor: ActorModel = Field(default_factory=ActorModel)
    context_enabled: bool = True


class ProposalDecisionBody(BaseModel):
    actor: ActorModel = Field(default_factory=ActorModel)
    comment: str = ""
    reason: str = ""


def create_app(app_context: Any) -> FastAPI:
    http_app = FastAPI(title="CCE JSON Adapter")

    @http_app.get("/health")
    def health():
        return {"status": "SERVING" if getattr(app_context, "ready", False) else "NOT_SERVING"}

    @http_app.post("/sources")
    def register_source(body: RegisterSourceBody):
        result = app_context.source_service.register_source(
            adapter=body.adapter,
            source_id=body.source_id,
            credential_ref=body.credential_ref,
            kind=body.kind or None,
            config=body.config,
        )
        return _source_result(result)

    @http_app.post("/sources/{source_id}/test")
    def test_connection(source_id: str, body: ActorBody | None = None):
        return _source_result(app_context.source_service.test_connection(source_id))

    @http_app.post("/sources/{source_id}/ingest")
    def trigger_ingestion(source_id: str, body: ActorBody | None = None):
        return _run_result(app_context.source_service.trigger_ingestion(source_id))

    @http_app.get("/ingestion-runs/{run_id}")
    def ingestion_status(run_id: str):
        return _run_result(app_context.source_service.get_ingestion_status(run_id))

    @http_app.get("/proposals")
    def list_proposals():
        return {"proposals": app_context.governance_service.list_proposals()}

    @http_app.get("/proposals/{proposal_id}")
    def get_proposal(proposal_id: str):
        return app_context.governance_service.get_proposal(proposal_id)

    @http_app.post("/proposals/{proposal_id}/approve")
    def approve_proposal(proposal_id: str, body: ProposalDecisionBody):
        return app_context.governance_service.approve_proposal(proposal_id, body.comment)

    @http_app.post("/proposals/{proposal_id}/reject")
    def reject_proposal(proposal_id: str, body: ProposalDecisionBody):
        return app_context.governance_service.reject_proposal(proposal_id, body.reason)

    @http_app.get("/packages")
    def list_packages():
        return {"packages": app_context.package_service.list_packages()}

    @http_app.get("/packages/{package_id}")
    def get_package(package_id: str):
        return app_context.package_service.get_package(package_id)

    @http_app.get("/packages/{package_id}/versions/{version}")
    def get_package_version(package_id: str, version: str):
        return app_context.package_service.get_package_version(package_id, version)

    @http_app.post("/query")
    def query(body: QueryBody):
        result = app_context.query_service.query(
            QueryRequest(
                question=body.question,
                actor_id=body.actor.actor_id,
                context_enabled=body.context_enabled,
            )
        )
        return {
            "answer": result.answer,
            "trace_id": result.trace_id or "",
            "citations": result.citations,
            "context_used": result.context_used,
            "applied_rule": result.applied_rule,
            "package_id": result.package_id,
            "package_version": result.package_version,
            "executed_sql": result.executed_sql,
            "approver": result.approver,
            "valid_until": result.valid_until,
            "confidence": result.confidence,
        }

    return http_app


def _source_result(result) -> dict:
    payload = {"source_id": result.source_id, "status": result.status}
    if result.error:
        payload["error"] = result.error
    return payload


def _run_result(result) -> dict:
    payload = {
        "ingestion_run_id": result.ingestion_run_id,
        "status": result.status,
        "objects_processed": result.objects_processed,
        "objects_failed": result.objects_failed,
    }
    if result.error:
        payload["error"] = result.error
    return payload
