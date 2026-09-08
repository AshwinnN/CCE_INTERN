"""Parallel governed/baseline runtime. Branch-local models keep OFF isolated."""

from datetime import datetime, timezone
from typing import Literal, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import Field

from cce.context_packages.models.assets import Model, PackageSnapshot
from cce.runtime.models import (
    AnswerRequest,
    AnswerResult,
    Citation,
    ContextReference,
    DomainCandidates,
    DomainResolution,
    DomainRoutingRequest,
    PackageResolution,
    ProofRequest,
    ProofResult,
    QueryBranchResult,
    QueryIntent,
    QueryRequest,
    QueryResponse,
    ResolvedContextBundle,
    SourceSchema,
    SourceSelection,
    SourceSelectionRequest,
    SQLGenerationRequest,
    VectorHit,
    WorkflowError,
)


class QueryWork(Model):
    request: QueryRequest
    trace_id: UUID
    intent: QueryIntent | None = None
    domain: DomainResolution = Field(default_factory=DomainResolution)
    package: PackageSnapshot | None = None
    errors: list[WorkflowError] = Field(default_factory=list)


class CCEQueryState(TypedDict, total=False):
    work: QueryWork
    context_on: QueryBranchResult
    context_off: QueryBranchResult
    response: QueryResponse


class BranchWork(Model):
    question: str
    trace_id: UUID
    domain_id: UUID
    intent: QueryIntent
    branch: Literal["ON", "OFF"]
    package: PackageSnapshot | None = None
    context: ResolvedContextBundle | None = None
    schemas: list[SourceSchema] = Field(default_factory=list)
    source: SourceSchema | None = None
    result: QueryBranchResult | None = None


class BranchState(TypedDict):
    work: BranchWork


class RuntimeOrchestrator:
    def __init__(self, settings, llm, domains, context, traces, index, sql):
        self.settings = settings
        self.llm = llm
        self.domains = domains
        self.context = context
        self.traces = traces
        self.index = index
        self.sql = sql
        self.on_graph = self._branch_graph()
        self.off_graph = self._branch_graph()
        g = StateGraph(CCEQueryState)
        g.add_node("create_trace", self._create_trace)
        g.add_node("parse_question", self._parse)
        g.add_node("resolve_domain", self._domain)
        g.add_node("load_active_package", self._package)
        g.add_node("context_on_subgraph", lambda s: self._branch(s, "ON"))
        g.add_node("context_off_subgraph", lambda s: self._branch(s, "OFF"))
        g.add_node("proof_classifier", self._proof)
        g.add_node("persist_trace_finalizer", self._persist)
        g.add_edge(START, "create_trace")
        g.add_edge("create_trace", "parse_question")
        g.add_edge("parse_question", "resolve_domain")
        g.add_edge("resolve_domain", "load_active_package")
        g.add_edge("load_active_package", "context_on_subgraph")
        g.add_edge("load_active_package", "context_off_subgraph")
        g.add_edge(["context_on_subgraph", "context_off_subgraph"], "proof_classifier")
        g.add_edge("proof_classifier", "persist_trace_finalizer")
        g.add_edge("persist_trace_finalizer", END)
        self.graph = g.compile()

    def _create_trace(self, state):
        work = QueryWork.model_validate(state["work"])
        self.traces.create_trace(work.trace_id, work.request)
        return {"work": work}

    def _persist(self, state):
        response = QueryResponse.model_validate(state["response"])
        self.traces.finish_trace(response)
        return {"response": response}

    def _call(self, trace, task, instruction, request, output_type):
        start = datetime.now(timezone.utc)
        result = None
        error = None
        try:
            result = self.llm.invoke(task, instruction, request, output_type)
            return result
        except Exception as exc:
            error = {"message": str(exc)}
            raise
        finally:
            self.traces.node(
                trace,
                output_type.__name__,
                start,
                datetime.now(timezone.utc),
                request,
                result,
                error,
                self.llm.model_name(task),
            )

    def _parse(self, state):
        w = QueryWork.model_validate(state["work"])
        try:
            w.intent = self._call(
                w.trace_id,
                "domain",
                "Parse question intent, entity mentions, and whether current database values are needed.",
                w.request,
                QueryIntent,
            )
        except Exception as exc:
            w.errors.append(WorkflowError(node="parse_question", message=str(exc)))
        return {"work": w}

    def _domain(self, state):
        w = state["work"]
        if not w.intent:
            return {"work": w}
        domains = self.domains.list()
        known = {d.domain_id: d for d in domains}
        if w.request.domain_id:
            if w.request.domain_id in known:
                d = known[w.request.domain_id]
                w.domain = DomainResolution(
                    domain_id=d.domain_id, name=d.name, status="SUCCESS"
                )
            else:
                w.domain.message = (
                    "Unknown or disabled domain; specify an existing domain."
                )
        else:
            try:
                result = self._call(
                    w.trace_id,
                    "domain",
                    "Rank existing domains for this question. Never create domain IDs.",
                    DomainRoutingRequest(question=w.request.question, domains=domains),
                    DomainCandidates,
                )
                candidates = [c for c in result.candidates if c.domain_id in known]
                best = max(candidates, key=lambda c: c.confidence, default=None)
                if best and best.confidence >= self.settings.domain_min_confidence:
                    w.domain = DomainResolution(
                        domain_id=best.domain_id,
                        name=known[best.domain_id].name,
                        confidence=best.confidence,
                        status="SUCCESS",
                    )
            except Exception as exc:
                w.errors.append(WorkflowError(node="resolve_domain", message=str(exc)))
        if w.domain.status != "SUCCESS":
            w.domain.message = (
                w.domain.message or "Please specify the domain for this question."
            )
        return {"work": w}

    def _package(self, state):
        w = state["work"]
        if w.domain.domain_id:
            w.package = self.context.active(w.domain.domain_id)
        return {"work": w}

    def _branch(self, state, branch):
        w = state["work"]
        key = "context_on" if branch == "ON" else "context_off"
        if w.domain.status != "SUCCESS":
            return {
                key: QueryBranchResult(
                    status="SKIPPED",
                    error_code="DOMAIN_UNRESOLVED",
                    message=w.domain.message,
                )
            }
        if branch == "OFF" and not self.settings.context_off_enabled:
            return {
                key: QueryBranchResult(
                    status="SKIPPED", message="Context OFF is disabled"
                )
            }
        if branch == "ON" and not w.request.context_enabled:
            return {
                key: QueryBranchResult(
                    status="SKIPPED", message="Context ON was disabled by the request"
                )
            }
        if branch == "ON" and not w.package:
            return {
                key: QueryBranchResult(
                    status="NO_ACTIVE_PACKAGE",
                    message="No active package found, so Context ON was not run.",
                )
            }
        # OFF never receives the package, even as a hidden branch-state field.
        work = BranchWork(
            question=w.request.question,
            trace_id=w.trace_id,
            domain_id=w.domain.domain_id,
            intent=w.intent,
            branch=branch,
            package=w.package if branch == "ON" else None,
        )
        try:
            result = (
                (self.on_graph if branch == "ON" else self.off_graph)
                .invoke({"work": work})["work"]
                .result
            )
        except Exception as exc:
            result = QueryBranchResult(
                status="FAILED", error_code="BRANCH_EXECUTION_FAILED", message=str(exc)
            )
        return {key: result}

    def _branch_graph(self):
        g = StateGraph(BranchState)
        for name in (
            "retrieve_and_assemble",
            "resolve_data_source",
            "run_sql_subgraph",
            "answer",
        ):
            fn = getattr(self, name)

            def node(state, fn=fn):
                return {"work": fn(BranchWork.model_validate(state["work"]))}

            g.add_node(name, node)
        g.add_edge(START, "retrieve_and_assemble")
        g.add_conditional_edges(
            "retrieve_and_assemble",
            lambda s: END if s["work"].result else "resolve_data_source",
        )
        g.add_conditional_edges(
            "resolve_data_source",
            lambda s: (
                END
                if s["work"].result
                else (
                    "run_sql_subgraph" if s["work"].intent.needs_live_data else "answer"
                )
            ),
        )
        g.add_conditional_edges(
            "run_sql_subgraph",
            lambda s: END if s["work"].result.status != "SUCCESS" else "answer",
        )
        g.add_edge("answer", END)
        return g.compile()

    def retrieve_and_assemble(self, w: BranchWork) -> BranchWork:
        if w.branch == "OFF":
            return w
        source_ids = {str(e.source_id) for a in w.package.assets for e in a.evidence}
        raw = self.index.search(
            w.question,
            limit=self.settings.retrieval_top_k
            * self.settings.retrieval_oversample_factor,
            metadata_filter={
                "domain_id": str(w.domain_id),
                "source_id": {"$in": sorted(source_ids)},
            },
        )
        hits = [
            VectorHit(
                memory_id=h["memory_id"],
                score=h["score"],
                content=h["chunk_text"],
                metadata=h.get("metadata", {}),
            )
            for h in raw
            if h["score"] >= self.settings.retrieval_min_score
            and str(h.get("metadata", {}).get("domain_id")) == str(w.domain_id)
            and str(h.get("metadata", {}).get("source_id", h.get("source_id")))
            in source_ids
        ]
        seeds = self.context.linked_assets(w.package, [h.memory_id for h in hits])
        linked = {e.agentic_memory_id for a in seeds for e in a.evidence}
        hits = [h for h in hits if h.memory_id in linked][
            : self.settings.retrieval_top_k
        ]
        if not hits:
            w.result = QueryBranchResult(
                status="INSUFFICIENT_CONTEXT",
                message="Not enough approved context is available. Request an admin/steward to add the required resource.",
            )
            return w
        seed_ids = {h.memory_id for h in hits}
        seeds = [
            a for a in seeds if any(e.agentic_memory_id in seed_ids for e in a.evidence)
        ]
        assets = self.context.expand(w.package, seeds, self.settings.graph_max_hops)
        w.context = ResolvedContextBundle(
            package_id=w.package.package_id,
            package_version_id=w.package.package_version_id,
            version=w.package.version,
            assets=assets,
            # Raw memory text is not authoritative and is never sent to reasoning.
            vector_hits=[h.model_copy(update={"content": ""}) for h in hits],
        )
        if not any(a.payload.asset_type == "VERIFIED_SQL" for a in assets):
            w.context.warnings.append("VERIFIED_SQL_EXAMPLES_MISSING")
        return w

    def resolve_data_source(self, w: BranchWork) -> BranchWork:
        if w.branch == "ON":
            ids = {
                a.payload.source_id
                for a in w.context.assets
                if a.payload.asset_type in ("SEMANTIC_MAPPING", "VERIFIED_SQL")
            }
            w.schemas = [self.traces.schema(i) for i in ids]
        else:
            w.schemas = self.traces.domain_schemas(w.domain_id)
        if not w.intent.needs_live_data:
            return w
        if len(w.schemas) == 1:
            w.source = w.schemas[0]
        elif len(w.schemas) > 1 and w.branch == "OFF":
            selected = self._call(
                w.trace_id,
                "domain",
                "Choose exactly one source if unambiguous; otherwise return ambiguous=true. Use only raw schemas.",
                SourceSelectionRequest(question=w.question, sources=w.schemas),
                SourceSelection,
            )
            if not selected.ambiguous:
                w.source = next(
                    (s for s in w.schemas if s.source_id == selected.source_id), None
                )
        if not w.source or not w.source.tables:
            w.result = QueryBranchResult(
                status="DATA_SOURCE_UNRESOLVED",
                error_code="DATA_SOURCE_UNRESOLVED",
                message="A single structured source could not be resolved safely.",
            )
        return w

    def run_sql_subgraph(self, w: BranchWork) -> BranchWork:
        result = self.sql.run(
            SQLGenerationRequest(
                question=w.question,
                schema_context=w.source,
                semantic_context=w.context if w.branch == "ON" else None,
            ),
            w.trace_id,
            w.branch,
        )
        w.result = QueryBranchResult(
            status=result.status,
            error_code=result.error_code,
            message=result.message,
            sql=result.sql,
            sql_attempts=result.attempts,
            rows=result.rows,
        )
        return w

    def answer(self, w: BranchWork) -> BranchWork:
        result = w.result or QueryBranchResult(status="SUCCESS")
        try:
            answer = self._call(
                w.trace_id,
                "answer",
                "Answer using only the provided evidence and SQL rows. State uncertainty and unresolved ambiguities. Include policy validity and conditions in applicability reasoning; never invent facts.",
                AnswerRequest(
                    question=w.question,
                    schemas=w.schemas,
                    context=w.context if w.branch == "ON" else None,
                    sql=result.sql,
                    rows=result.rows,
                ),
                AnswerResult,
            )
            result.answer = answer.answer
        except Exception as exc:
            result.status = "FAILED"
            result.error_code = "ANSWER_GENERATION_FAILED"
            result.message = str(exc)
        if w.context:
            result.warnings = w.context.warnings
            result.context_used = [
                ContextReference(
                    asset_id=a.asset_id,
                    asset_revision_id=a.asset_revision_id,
                    canonical_key=a.payload.canonical_key,
                )
                for a in w.context.assets
            ]
            result.citations = [
                Citation(
                    asset_id=a.asset_id,
                    asset_revision_id=a.asset_revision_id,
                    package_version_id=w.context.package_version_id,
                    evidence=e,
                )
                for a in w.context.assets
                for e in a.evidence
            ]
        if result.sql and w.source:
            from cce.runtime.sql_guard import referenced_tables
            used_tables = referenced_tables(result.sql, w.source)
            result.citations.append(
                Citation(
                    source_id=w.source.source_id,
                    tables=[
                        f"{t.database}.{t.schema_name}.{t.name}"
                        for t in used_tables
                    ],
                    database=used_tables[0].database if used_tables else None,
                    schema_name=used_tables[0].schema_name if used_tables else None,
                    sql=result.sql,
                    sql_attempt_id=result.sql_attempts[-1].attempt_id,
                )
            )
        w.result = result
        return w

    def _proof(self, state):
        w = state["work"]
        on = state["context_on"]
        off = state["context_off"]
        proof = ProofResult()
        if (
            on.status == "SUCCESS"
            and off.status == "SUCCESS"
            and on.answer
            and off.answer
        ):
            try:
                proof = self._call(
                    w.trace_id,
                    "proof",
                    "Compare the two answers. Improvement classifications are interpretations, not measured accuracy. Do not claim benchmark lift without ground truth.",
                    ProofRequest(context_on=on, context_off=off),
                    ProofResult,
                )
                proof.comparable = True
            except Exception as exc:
                w.errors.append(
                    WorkflowError(node="proof_classifier", message=str(exc))
                )
        package = (
            PackageResolution(
                package_id=w.package.package_id,
                package_version_id=w.package.package_version_id,
                version=w.package.version,
                status="ACTIVE",
            )
            if w.package
            else PackageResolution()
        )
        return {
            "response": QueryResponse(
                trace_id=w.trace_id,
                question=w.request.question,
                domain=w.domain,
                package=package,
                context_on=on,
                context_off=off,
                proof=proof,
                errors=w.errors,
            )
        }

    def run(self, request: QueryRequest) -> QueryResponse:
        trace_id = uuid4()
        try:
            response = self.graph.invoke(
                {"work": QueryWork(request=request, trace_id=trace_id)},
                config={"max_concurrency": 2},
            )["response"]
        except Exception as exc:
            response = QueryResponse(
                trace_id=trace_id,
                question=request.question,
                domain=DomainResolution(),
                context_on=QueryBranchResult(status="FAILED", message=str(exc)),
                context_off=QueryBranchResult(status="FAILED", message=str(exc)),
                errors=[WorkflowError(node="runtime", message=str(exc))],
            )
            self.traces.finish_trace(response)
            raise RuntimeError(f"CCE runtime infrastructure failure; trace_id={trace_id}") from exc
        if not self.settings.query_include_rows:
            response = response.model_copy(deep=True)
            response.context_on.rows = []
            response.context_off.rows = []
        return response
