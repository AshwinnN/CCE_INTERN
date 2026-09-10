from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from cce.config.settings import Settings
from cce.governance.models import WorkspaceCreate
from cce.runtime.compound import CompoundQuery, NoActivePackage
from cce.runtime.models import (
    AnswerRequest,
    AnswerResult,
    ColumnSchema,
    ProofResult,
    QueryIntent,
    QueryRequest,
    SourceSchema,
    SQLCandidate,
    SQLErrorAnalysis,
    SQLErrorRequest,
    SQLGenerationRequest,
    TableSchema,
    WorkspaceInfo,
)
from cce.runtime.orchestrator import RuntimeOrchestrator
from cce.runtime.sql_guard import guard_query
from cce.runtime.sql_pipeline import SQLPipeline
from test_lifecycle import ADMIN, approve_all, candidate, finish, setup_source, start


class LLM:
    def __init__(self, workspace, barrier=None):
        self.workspace = workspace
        self.requests = []
        self.barrier = barrier

    def model_name(self, task):
        return "fixture"

    def invoke(self, task, instruction, request, output):
        self.requests.append(request)
        if output is QueryIntent:
            return QueryIntent(intent="definition", needs_live_data=False)
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
        self.graph_calls = 0

    def search(self, *args, **kwargs):
        return self.hits

    def graph(self, *args, **kwargs):
        self.graph_calls += 1
        return {'entities': [
            {'entity_id': 'scoped', 'name': 'Scoped concept', 'source_memories': [self.hits[0]['memory_id']]}
        ] if self.hits else [], 'relationships': [], 'memories': []}


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


def test_parallel_runtime_governance_filter_workspace_failures_and_traces(system):
    s = system
    workspace, source = setup_source(s)
    run, job, items = start(s, source)
    c = candidate(workspace, items[0], run)
    finish(s, job, items, [[c]])
    batch = s.governance.promote(run.ingestion_run_id, workspace.workspace_uuid)
    approve_all(s, batch)
    package = s.context.active(workspace.workspace_uuid)
    winfo = WorkspaceInfo(
        workspace_uuid=workspace.workspace_uuid,
        workspace_id=workspace.workspace_id,
        name=workspace.name,
    )
    hit = {
        "memory_id": c.evidence[0].agentic_memory_id,
        "score": 0.95,
        "chunk_text": "Source passage supporting a policy answer",
        "metadata": {"source_id": str(source), "workspace_uuid": str(workspace.workspace_uuid)},
    }
    index = Index([hit])
    llm = LLM(workspace, Barrier(2))
    settings = Settings()
    runtime = RuntimeOrchestrator(
        settings, llm, s.workspaces, s.context, s.traces, index, None
    )
    response = runtime.run(
        QueryRequest(question="Define term", workspace_id=workspace.workspace_id),
        winfo,
        package,
    )
    assert (
        response.context_on.status == "SUCCESS"
        and response.context_off.status == "SUCCESS"
    )
    assert response.proof.classification == "DIFFERENT"
    answers = [r for r in llm.requests if isinstance(r, AnswerRequest)]
    assert len(answers) == 2 and sum(r.context is None for r in answers) == 1
    assert all(
        h.content == hit['chunk_text'] for r in answers if r.context for h in r.context.vector_hits
    )
    assert index.graph_calls == 1
    assert next(r for r in answers if r.context).context.graph.entities[0].entity_id == 'scoped'
    assert response.context_on.citations and response.context_on.context_used
    with s.db.transaction() as cur:
        cur.execute(
            "SELECT status FROM query_trace WHERE trace_id=%s",
            (str(response.trace_id),),
        )
        assert cur.fetchone()["status"] == "SUCCESS"
    # Source passages need not have an approved asset. Workspace and score gates remain.
    llm.barrier = None
    index.hits = [{**hit, 'memory_id': 'unapproved-memory'}]
    request = QueryRequest(question='Define term', workspace_id=workspace.workspace_id)
    assert runtime.run(request, winfo, package).context_on.status == 'SUCCESS'
    for bad in ({**hit, 'metadata': {**hit['metadata'], 'workspace_uuid': str(uuid4())}}, {**hit, "score": 0.1}):
        index.hits = [bad]
        response = runtime.run(request, winfo, package)
        assert (
            response.context_on.status == "INSUFFICIENT_CONTEXT"
            and response.context_off.status == "SUCCESS"
        )
        assert response.proof.classification == "NOT_COMPARABLE"


def test_compound_query_rejects_missing_package_and_unknown_workspace(system):
    s = system
    workspace, _source = setup_source(s)

    class Runtime:
        traces = s.traces

    class Feedback:
        def retrieve(self, workspace_uuid, question):
            return []

    compound = CompoundQuery(Runtime(), s.workspaces, s.context, Feedback())
    with pytest.raises(NoActivePackage):
        compound.run(QueryRequest(question="Define term", workspace_id=workspace.workspace_id))
    with pytest.raises(KeyError):
        compound.run(QueryRequest(question="Define term", workspace_id="missing_workspace"))


def test_sql_shared_retry_budget_guard_execution_and_attempt_persistence(system):
    s = system
    workspace = s.workspaces.create(WorkspaceCreate(name="SQL pipeline test"), ADMIN)
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
    s.traces.create_trace(
        trace, QueryRequest(question="Current value", workspace_id=workspace.workspace_id)
    )
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
    s.traces.create_trace(
        trace2, QueryRequest(question="Current value", workspace_id=workspace.workspace_id)
    )
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
    s.traces.create_trace(
        trace3, QueryRequest(question="Current value", workspace_id=workspace.workspace_id)
    )
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
