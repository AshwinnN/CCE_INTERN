from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from cce.config.settings import Settings
from cce.governance.models import DomainCreate
from cce.runtime.models import (
    AnswerRequest,
    AnswerResult,
    ColumnSchema,
    DomainCandidate,
    DomainCandidates,
    ProofResult,
    QueryIntent,
    QueryRequest,
    SourceSchema,
    SQLCandidate,
    SQLErrorAnalysis,
    SQLErrorRequest,
    SQLGenerationRequest,
    TableSchema,
)
from cce.runtime.orchestrator import RuntimeOrchestrator
from cce.runtime.sql_guard import guard_query
from cce.runtime.sql_pipeline import SQLPipeline
from test_lifecycle import ADMIN, approve_all, candidate, finish, setup_source, start


class LLM:
    def __init__(self, domain, barrier=None):
        self.domain = domain
        self.requests = []
        self.barrier = barrier

    def model_name(self, task):
        return "fixture"

    def invoke(self, task, instruction, request, output):
        self.requests.append(request)
        if output is QueryIntent:
            return QueryIntent(intent="definition", needs_live_data=False)
        if output is DomainCandidates:
            return DomainCandidates(
                candidates=[
                    DomainCandidate(
                        domain_id=self.domain.domain_id,
                        confidence=0.9,
                        rationale="fixture",
                    )
                ]
            )
        if output is AnswerResult:
            if self.barrier:
                self.barrier.wait(timeout=3)
            return AnswerResult(
                answer="Approved definition"
                if request.context
                else "Schema-only baseline"
            )
        if output is ProofResult:
            return ProofResult(
                classification="DIFFERENT",
                comparable=True,
                explanation="Different supplied evidence",
            )
        raise AssertionError(output)


class Index:
    def __init__(self, hits):
        self.hits = hits

    def search(self, *args, **kwargs):
        return self.hits


class SQLLLM:
    def __init__(self, queries):
        self.queries = iter(queries)
        self.repairs = []

    def invoke(self, task, instruction, request, output):
        if output is SQLCandidate:
            return SQLCandidate(sql=next(self.queries))
        self.repairs.append(request)
        assert isinstance(request, SQLErrorRequest)
        return SQLErrorAnalysis(
            error_type="SQL",
            error_message=request.error,
            correction_guidance="Use the known read-only table",
        )


class Executor:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def execute(self, schema, sql, timeout, max_rows):
        self.calls.append(sql)
        if self.fail:
            self.fail = False
            raise RuntimeError("Database execution failure")
        return [{"VALUE": 82}]


def test_parallel_runtime_governance_filter_domain_failures_and_traces(system):
    s = system
    domain, source = setup_source(s)
    run, job, items = start(s, source)
    c = candidate(domain, items[0], run)
    finish(s, job, items, [[c]])
    batch = s.governance.promote(run.ingestion_run_id, domain.domain_id)
    approve_all(s, batch)
    hit = {
        "memory_id": c.evidence[0].agentic_memory_id,
        "score": 0.95,
        "chunk_text": "RAW CONTENT MUST NOT GOVERN",
        "metadata": {"source_id": str(source), "domain_id": str(domain.domain_id)},
    }
    index = Index([hit])
    llm = LLM(domain, Barrier(2))
    settings = Settings()
    runtime = RuntimeOrchestrator(
        settings, llm, s.domains, s.context, s.traces, index, None
    )
    response = runtime.run(
        QueryRequest(question="Define term", domain_id=domain.domain_id)
    )
    assert (
        response.context_on.status == "SUCCESS"
        and response.context_off.status == "SUCCESS"
    )
    assert response.proof.classification == "DIFFERENT"
    answers = [r for r in llm.requests if isinstance(r, AnswerRequest)]
    assert len(answers) == 2 and sum(r.context is None for r in answers) == 1
    assert all(
        h.content == "" for r in answers if r.context for h in r.context.vector_hits
    )
    assert response.context_on.citations and response.context_on.context_used
    with s.db.transaction() as cur:
        cur.execute(
            "SELECT status FROM query_trace WHERE trace_id=%s",
            (str(response.trace_id),),
        )
        assert cur.fetchone()["status"] == "SUCCESS"
    # Unlinked or low-score memory must not reach the answer model; OFF remains available.
    llm.barrier = None
    for bad in ({**hit, "memory_id": "unapproved-memory"}, {**hit, "score": 0.1}):
        index.hits = [bad]
        response = runtime.run(QueryRequest(question="Define term"))
        assert (
            response.context_on.status == "INSUFFICIENT_CONTEXT"
            and response.context_off.status == "SUCCESS"
        )
        assert response.proof.classification == "NOT_COMPARABLE"
    other = s.domains.create(DomainCreate(name="No package"), ADMIN)
    response = runtime.run(
        QueryRequest(question="Define term", domain_id=other.domain_id)
    )
    assert (
        response.context_on.status == "NO_ACTIVE_PACKAGE"
        and response.context_off.status == "SUCCESS"
    )
    response = runtime.run(QueryRequest(question="Define term", domain_id=uuid4()))
    assert response.domain.status == "DOMAIN_UNRESOLVED"
    assert response.context_on.status == response.context_off.status == "SKIPPED"
    assert response.domain.message


def test_sql_shared_retry_budget_guard_execution_and_attempt_persistence(system):
    s = system
    source = uuid4()
    schema = SourceSchema(
        source_id=source,
        tables=[
            TableSchema(
                database="DB",
                schema_name="PUBLIC",
                name="METRIC",
                columns=[ColumnSchema(name="VALUE", data_type="NUMBER")],
            )
        ],
    )
    trace = uuid4()
    s.traces.create_trace(trace, QueryRequest(question="Current value"))
    llm = SQLLLM(
        [
            "SELECT (",
            "DELETE FROM DB.PUBLIC.METRIC",
            "SELECT VALUE FROM DB.PUBLIC.METRIC",
        ]
    )
    executor = Executor()
    pipeline = SQLPipeline(Settings(), llm, executor, s.traces)
    result = pipeline.run(
        SQLGenerationRequest(question="Current value", schema_context=schema),
        trace,
        "ON",
    )
    assert (
        result.status == "SUCCESS"
        and len(result.attempts) == 3
        and len(executor.calls) == 1
    )
    assert result.attempts[0].parse_result.valid is False
    assert result.attempts[1].guard_result.valid is False
    assert len(llm.repairs) == 2
    with s.db.transaction() as cur:
        cur.execute(
            "SELECT count(*) n FROM sql_attempt WHERE trace_id=%s", (str(trace),)
        )
        assert cur.fetchone()["n"] == 3
    trace2 = uuid4()
    s.traces.create_trace(trace2, QueryRequest(question="Current value"))
    llm2 = SQLLLM(["SELECT VALUE FROM METRIC"] * 2)
    result = SQLPipeline(
        replace(Settings(), sql_max_retries=1), llm2, Executor(fail=True), s.traces
    ).run(
        SQLGenerationRequest(question="Current value", schema_context=schema),
        trace2,
        "OFF",
    )
    assert result.status == "SUCCESS" and len(result.attempts) == 2
    assert result.attempts[0].database_error == "Database execution failure"
    trace3 = uuid4()
    s.traces.create_trace(trace3, QueryRequest(question="Current value"))
    result = SQLPipeline(
        replace(Settings(), sql_max_retries=1),
        SQLLLM(["DROP TABLE METRIC"] * 2),
        Executor(),
        s.traces,
    ).run(
        SQLGenerationRequest(question="Current value", schema_context=schema),
        trace3,
        "OFF",
    )
    assert result.error_code == "RETRIES_EXHAUSTED" and len(result.attempts) == 2
    for query in [
        "SELECT 1; DELETE FROM METRIC",
        "WITH x AS (DELETE FROM METRIC) SELECT * FROM x",
        "SELECT * FROM OTHER.PUBLIC.METRIC",
        "SELECT malicious_udf(VALUE) FROM METRIC",
        'SELECT VALUE FROM "metric"',
    ]:
        with pytest.raises((ValueError, PermissionError)):
            guard_query(query, schema)
    assert "LIMIT 1000" in guard_query(
        "WITH x AS (SELECT VALUE FROM METRIC) SELECT * FROM x", schema
    )
