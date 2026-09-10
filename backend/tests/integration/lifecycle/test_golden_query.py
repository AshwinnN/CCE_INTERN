"""Golden query through real governance, PostgreSQL metadata, SQL graph and compound atomization.
Provider/model outputs are explicit fixtures; this is not a hosted accuracy benchmark.
"""

from dataclasses import replace
from uuid import uuid4

from cce.config.settings import Settings
from cce.context_packages.models.assets import (
    Entity,
    PolicyRule,
    SemanticMapping,
    VerifiedSQL,
)
from cce.runtime.compound import CompoundQuery
from cce.runtime.models import (
    AnswerResult,
    AtomicQuestions,
    ProofResult,
    QueryIntent,
    QueryRequest,
    SQLCandidate,
)
from cce.runtime.orchestrator import RuntimeOrchestrator
from cce.runtime.sql_pipeline import SQLPipeline
from test_lifecycle import approve_all, candidate, finish, setup_source, start
from test_runtime import Executor, Index


class NoOpFeedback:
    def retrieve(self, workspace_uuid, question):
        return []


class GoldenLLM:
    def model_name(self, task):
        return "fixture-shared-answer-model"

    def invoke(self, task, instruction, request, output):
        if output is AtomicQuestions:
            return AtomicQuestions(questions=[request.question])
        if output is QueryIntent:
            return QueryIntent(intent="SLA compliance", needs_live_data=True)
        if output is SQLCandidate:
            if request.semantic_context is None:
                assert not hasattr(request.schema_context, "assets")
            return SQLCandidate(
                sql="SELECT on_time_rate FROM DB.PUBLIC.delivery_performance"
            )
        if output is AnswerResult and task == "answer":
            assert request.rows == [{"VALUE": 82}]
            if request.context:
                rules = [
                    a.payload
                    for a in request.context.assets
                    if a.payload.asset_type == "POLICY_RULE"
                ]
                assert rules and rules[0].valid_until == "2026-09-30"
                return AnswerResult(
                    answer="YES: 82% exceeds the approved 80% customer exception; valid through September 30."
                )
            return AnswerResult(
                answer="82% is the current performance. The schema alone does not establish an applicable SLA threshold."
            )
        if output is AnswerResult and task == "synthesis":
            return AnswerResult(answer=request["successful_on_answers"][0]["answer"])
        if output is ProofResult:
            return ProofResult(
                classification="DIFFERENT",
                comparable=True,
                explanation="Only ON has an approved customer exception. No measured accuracy claim.",
            )
        raise AssertionError((task, output))


def test_golden_live_query_and_row_visibility(system):
    s = system
    workspace, source = setup_source(s)
    ns, sc, snapshot, table, col = (uuid4() for _ in range(5))
    with s.db.transaction() as cur:
        cur.execute(
            "UPDATE cce_source SET kind='structured',source_type='snowflake' WHERE source_id=%s",
            (str(source),),
        )
        cur.execute(
            "INSERT INTO cce_namespace(namespace_id,source_id,namespace_name,namespace_type) VALUES(%s,%s,'DB','catalog')",
            (str(ns), str(source)),
        )
        cur.execute(
            "INSERT INTO cce_schema(schema_id,namespace_id,schema_name) VALUES(%s,%s,'PUBLIC')",
            (str(sc), str(ns)),
        )
        cur.execute(
            "INSERT INTO cce_schema_snapshot(snapshot_id,source_id,schema_id,schema_hash,status) VALUES(%s,%s,%s,'hash','SUCCESS')",
            (str(snapshot), str(source), str(sc)),
        )
        cur.execute(
            "INSERT INTO cce_table(table_id,snapshot_id,schema_id,table_name) VALUES(%s,%s,%s,'delivery_performance')",
            (str(table), str(snapshot), str(sc)),
        )
        cur.execute(
            "INSERT INTO cce_column(column_id,snapshot_id,table_id,column_name,ordinal_position,data_type,native_data_type) VALUES(%s,%s,%s,'on_time_rate',1,'NUMBER','NUMBER')",
            (str(col), str(snapshot), str(table)),
        )
    run, job, items = start(s, source)
    glossary = candidate(workspace, items[0], run)
    glossary.payload.dependencies = ["customer", "mapping", "rule", "sql"]
    payloads = [
        Entity(canonical_key="customer", name="Customer ABC", entity_type="customer"),
        SemanticMapping(
            canonical_key="mapping",
            concept="delivery performance",
            source_id=source,
            database="DB",
            schema_name="PUBLIC",
            table="delivery_performance",
            columns=["on_time_rate"],
        ),
        PolicyRule(
            canonical_key="rule",
            rule="Customer ABC threshold is 80%",
            entity_keys=["customer"],
            valid_until="2026-09-30",
        ),
        VerifiedSQL(
            canonical_key="sql",
            source_id=source,
            sql="SELECT on_time_rate FROM DB.PUBLIC.delivery_performance",
            description="Analyst example",
        ),
    ]
    candidates = [glossary] + [candidate(workspace, items[0], run, p) for p in payloads]
    finish(s, job, items, [candidates])
    batch = s.governance.promote(run.ingestion_run_id, workspace.workspace_uuid)
    approve_all(s, batch)
    package = s.context.active(workspace.workspace_uuid)
    assert package and len(package.assets) == 5
    index = Index(
        [
            {
                "memory_id": glossary.evidence[0].agentic_memory_id,
                "score": 0.95,
                "chunk_text": "untrusted retrieval content",
                "metadata": {
                    "workspace_uuid": str(workspace.workspace_uuid),
                    "source_id": str(source),
                },
            }
        ]
    )
    settings = replace(Settings(), query_include_rows=False)
    llm = GoldenLLM()
    executor = Executor()
    sql = SQLPipeline(settings, llm, executor, s.traces)
    runtime = RuntimeOrchestrator(
        settings, llm, s.workspaces, s.context, s.traces, index, sql
    )
    compound = CompoundQuery(runtime, s.workspaces, s.context, NoOpFeedback())
    response = compound.run(
        QueryRequest(
            question="Is Customer ABC meeting its delivery SLA?",
            workspace_id=workspace.workspace_id,
        )
    )
    assert response.status == "SUCCESS"
    atomic = response.atomic_results[0]
    assert atomic.context_on.status == atomic.context_off.status == "SUCCESS"
    assert atomic.context_on.answer.startswith("YES")
    assert atomic.context_off.answer.startswith("82%")
    assert not atomic.context_on.rows and not atomic.context_off.rows
    assert len(executor.calls) == 2
    assert atomic.context_on.sql_attempts and atomic.context_on.citations
    assert atomic.proof.classification == "DIFFERENT"
    assert response.answer.startswith("YES")
    with s.db.transaction() as cur:
        cur.execute(
            "SELECT status FROM query_trace WHERE trace_id=%s", (str(response.trace_id),)
        )
        assert cur.fetchone()["status"] == "SUCCESS"
        # The API response hides rows (query_include_rows=False); the persisted
        # atomic-branch trace still records the real rows for audit purposes.
        cur.execute(
            "SELECT response FROM query_trace WHERE trace_id=%s", (str(atomic.trace_id),)
        )
        stored = cur.fetchone()["response"]
        assert stored["context_on"]["rows"] == [{"VALUE": 82}]
