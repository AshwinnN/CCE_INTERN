"""Thin production transport. Actor claims must come from an authenticated gateway."""

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cce.context_packages.models.assets import Asset, PackageSnapshot
from cce.governance.models import (
    Actor,
    Domain,
    DomainCreate,
    Proposal,
    ProposalFilter,
    ProposalStatus,
    ReviewRequest,
)
from cce.runtime.models import QueryRequest, QueryResponse
from cce.sources.models import IngestionRunResult, SourceOperationResult


class ActorModel(BaseModel):
    actor_id: str = ""
    roles: list[str] = Field(default_factory=list)


class ActorBody(BaseModel):
    actor: ActorModel = Field(default_factory=ActorModel)


class RegisterSourceBody(ActorBody):
    adapter: str
    source_id: str
    credential_ref: str = ""
    kind: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


class QueryBody(ActorBody):
    question: str = Field(min_length=1, max_length=16000)
    domain_id: UUID | None = None
    context_enabled: bool = True


class RetrieveBody(BaseModel):
    question: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)
    graph_depth: int = Field(default=2, ge=1, le=10)


class ProposalDecisionBody(ActorBody):
    comment: str = ""
    reason: str = ""


class ProposalEditBody(ActorBody):
    payload: Asset
    comment: str = ""


class DomainBody(DomainCreate):
    actor: Actor


class ProposalList(BaseModel):
    proposals: list[Proposal]


class PackageInfo(BaseModel):
    package_id: UUID
    domain_id: UUID
    name: str


class PackageList(BaseModel):
    packages: list[PackageInfo]


def create_app(app_context: Any) -> FastAPI:
    app = FastAPI(title="CCE governed context API")

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    async def forbidden(request: Request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return {
            "status": "SERVING"
            if getattr(app_context, "ready", False)
            else "NOT_SERVING"
        }

    @app.post("/domains", response_model=Domain)
    def create_domain(body: DomainBody):
        return app_context.domain_repository.create(
            DomainCreate(**body.model_dump(exclude={"actor"})), body.actor
        )

    @app.get("/domains", response_model=list[Domain])
    def domains():
        return app_context.domain_repository.list()

    @app.post(
        "/sources",
        response_model=SourceOperationResult,
        response_model_exclude_none=True,
    )
    def register_source(body: RegisterSourceBody):
        return app_context.source_service.register_source(
            adapter=body.adapter,
            source_id=body.source_id,
            credential_ref=body.credential_ref,
            kind=body.kind or None,
            config=body.config,
        )

    @app.get("/sources")
    def sources():
        return app_context.source_service.list_sources()

    @app.post(
        "/sources/{source_id}/test",
        response_model=SourceOperationResult,
        response_model_exclude_none=True,
    )
    def test_source(source_id: str, body: ActorBody | None = None):
        return app_context.source_service.test_connection(source_id)

    @app.post(
        "/sources/{source_id}/ingest",
        response_model=IngestionRunResult,
        response_model_exclude_none=True,
    )
    def ingest(source_id: str, body: ActorBody | None = None):
        return app_context.source_service.trigger_ingestion(source_id)

    @app.get(
        "/ingestion-runs/{run_id}",
        response_model=IngestionRunResult,
        response_model_exclude_none=True,
    )
    def ingestion_status(run_id: UUID):
        return app_context.source_service.get_ingestion_status(str(run_id))

    @app.get("/proposals", response_model=ProposalList)
    def proposals(
        status: ProposalStatus | None = None,
        domain_id: UUID | None = None,
        proposal_batch_id: UUID | None = None,
    ):
        return ProposalList(
            proposals=app_context.governance_service.list_proposals(
                ProposalFilter(
                    status=status,
                    domain_id=domain_id,
                    proposal_batch_id=proposal_batch_id,
                )
            )
        )

    @app.get("/proposals/{proposal_id}", response_model=Proposal)
    def proposal(proposal_id: UUID):
        return app_context.governance_service.get_proposal(proposal_id)

    @app.patch("/proposals/{proposal_id}", response_model=Proposal)
    def edit(proposal_id: UUID, body: ProposalEditBody):
        return app_context.governance_service.edit_proposal(
            ReviewRequest(
                proposal_id=proposal_id,
                actor=Actor(**body.actor.model_dump()),
                payload=body.payload,
                comment=body.comment,
            )
        )

    @app.post("/proposals/{proposal_id}/approve", response_model=Proposal)
    def approve(proposal_id: UUID, body: ProposalDecisionBody):
        return app_context.governance_service.approve_proposal(
            ReviewRequest(
                proposal_id=proposal_id,
                actor=Actor(**body.actor.model_dump()),
                comment=body.comment,
            )
        )

    @app.post("/proposals/{proposal_id}/reject", response_model=Proposal)
    def reject(proposal_id: UUID, body: ProposalDecisionBody):
        return app_context.governance_service.reject_proposal(
            ReviewRequest(
                proposal_id=proposal_id,
                actor=Actor(**body.actor.model_dump()),
                comment=body.reason or body.comment,
            )
        )

    @app.get("/packages", response_model=PackageList)
    def packages():
        return PackageList(packages=app_context.package_service.list_packages())

    @app.get("/packages/{domain_id}/active", response_model=PackageSnapshot | None)
    def active(domain_id: UUID):
        return app_context.package_service.active(domain_id)

    @app.get("/packages/{package_id}", response_model=PackageInfo)
    def package(package_id: UUID):
        return app_context.package_service.get_package(package_id)

    @app.get(
        "/packages/{package_id}/versions/{version}", response_model=PackageSnapshot
    )
    def version(package_id: UUID, version: str):
        return app_context.package_service.get_package_version(package_id, version)

    @app.post("/query", response_model=QueryResponse)
    def query(body: QueryBody):
        return app_context.query_service.query(
            QueryRequest(
                question=body.question,
                actor_id=body.actor.actor_id or None,
                domain_id=body.domain_id,
                context_enabled=body.context_enabled,
            )
        )

    @app.post("/retrieve")
    def retrieve(body: RetrieveBody):
        return app_context.retrieval_service.retrieve(
            body.question, limit=body.limit, graph_depth=body.graph_depth
        )

    return app
