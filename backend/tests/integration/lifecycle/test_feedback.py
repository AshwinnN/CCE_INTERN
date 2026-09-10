"""Feedback persistence (PostgreSQL) and retrieval (through the same index-client
boundary used everywhere else -- never a bespoke pgvector column, per
ADR-003/ADR-005) scoped to one Workspace."""
from uuid import uuid4

import pytest
from cce.governance.models import WorkspaceCreate
from cce.persistence.postgres.lifecycle_db import json_param
from cce.runtime.feedback import FeedbackAnalysis, FeedbackRequest, FeedbackService
from test_lifecycle import ADMIN


class FakeIndexClient:
    def __init__(self):
        self.docs = []

    def index(self, payload):
        self.docs.append(payload)
        return {"status": "indexed", "indexed": 1}

    def search(self, query, *, limit, metadata_filter):
        def matches(doc):
            return all(doc["metadata"].get(k) == v for k, v in metadata_filter.items())

        hits = [d for d in self.docs if matches(d)]
        return [
            {"memory_id": d["document_id"], "chunk_text": d["blocks"][0]["text"], "metadata": d["metadata"]}
            for d in hits[:limit]
        ]


class FakeLLM:
    def __init__(self, confidence):
        self.confidence = confidence
        self.calls = 0

    def invoke(self, task, instruction, request, output):
        self.calls += 1
        assert output is FeedbackAnalysis
        return FeedbackAnalysis(
            issue_category="INCOMPLETE_ANSWER",
            critique="Missed the exception clause",
            lesson="Always check for approved exceptions before answering",
            confidence=self.confidence,
        )


def _seed_trace(s, workspace, trace_id, question="Is Customer ABC meeting its SLA?", answer="YES: 82% meets the exception."):
    with s.db.transaction() as cur:
        cur.execute(
            """INSERT INTO query_trace(trace_id,question,actor_id,workspace_uuid,status,response,finished_at)
            VALUES(%s,%s,'tester',%s,'SUCCESS',%s,now())""",
            (
                str(trace_id),
                question,
                str(workspace.workspace_uuid),
                json_param(
                    {
                        "question": question,
                        "answer": answer,
                        "package": {"package_version_id": None},
                        "atomic_results": [],
                        "citations": [],
                    }
                ),
            ),
        )


def test_upvote_is_persisted_and_retrievable_as_positive_example(system):
    s = system
    workspace = s.workspaces.create(WorkspaceCreate(name="Feedback upvote test"), ADMIN)
    trace_id = uuid4()
    _seed_trace(s, workspace, trace_id)
    index = FakeIndexClient()
    service = FeedbackService(s.db, FakeLLM(0.0), index, top_k=5)
    result = service.submit(workspace.workspace_uuid, FeedbackRequest(trace_id=str(trace_id), rating="GOOD"), ADMIN)
    assert result["rating"] == "GOOD" and result["lesson_eligible"] is True
    with s.db.transaction() as cur:
        cur.execute("SELECT rating, lesson_eligible FROM query_feedback WHERE trace_id=%s", (str(trace_id),))
        row = cur.fetchone()
        assert row["rating"] == "GOOD" and row["lesson_eligible"] is True
    lessons = service.retrieve(workspace.workspace_uuid, "Is Customer ABC meeting its SLA?")
    assert len(lessons) == 1
    assert lessons[0]["label"].startswith("GOOD")
    assert lessons[0]["example"] == "YES: 82% meets the exception."


def test_downvote_with_comment_is_eligible_without_llm_call(system):
    s = system
    workspace = s.workspaces.create(WorkspaceCreate(name="Feedback downvote comment test"), ADMIN)
    trace_id = uuid4()
    _seed_trace(s, workspace, trace_id)
    index = FakeIndexClient()
    llm = FakeLLM(0.0)
    service = FeedbackService(s.db, llm, index, top_k=5)
    result = service.submit(
        workspace.workspace_uuid,
        FeedbackRequest(trace_id=str(trace_id), rating="BAD", comment="Missed the exception clause entirely"),
        ADMIN,
    )
    assert result["lesson_eligible"] is True
    assert llm.calls == 0  # explicit comment means no LLM critique is needed
    lessons = service.retrieve(workspace.workspace_uuid, "Is Customer ABC meeting its SLA?")
    assert len(lessons) == 1
    assert lessons[0]["label"].startswith("BAD")
    assert lessons[0]["example"] == "Missed the exception clause entirely"


def test_downvote_without_comment_triggers_llm_critique_and_confidence_gate(system):
    s = system
    workspace = s.workspaces.create(WorkspaceCreate(name="Feedback downvote critique test"), ADMIN)

    high_trace = uuid4()
    _seed_trace(s, workspace, high_trace)
    high_service = FeedbackService(s.db, FakeLLM(0.85), FakeIndexClient(), top_k=5)
    high_result = high_service.submit(workspace.workspace_uuid, FeedbackRequest(trace_id=str(high_trace), rating="BAD"), ADMIN)
    assert high_result["lesson_eligible"] is True
    assert high_result["inference_confidence"] == 0.85
    assert len(high_service.index_client.docs) == 1  # eligible -> indexed for future few-shot use

    low_trace = uuid4()
    _seed_trace(s, workspace, low_trace)
    low_service = FeedbackService(s.db, FakeLLM(0.4), FakeIndexClient(), top_k=5)
    low_result = low_service.submit(workspace.workspace_uuid, FeedbackRequest(trace_id=str(low_trace), rating="BAD"), ADMIN)
    assert low_result["lesson_eligible"] is False
    with s.db.transaction() as cur:
        cur.execute("SELECT lesson_eligible, inference_confidence FROM query_feedback WHERE trace_id=%s", (str(low_trace),))
        row = cur.fetchone()
        assert row["lesson_eligible"] is False and row["inference_confidence"] == 0.4
    assert len(low_service.index_client.docs) == 0  # persisted, but never indexed as a future few-shot lesson
    assert low_service.retrieve(workspace.workspace_uuid, "Is Customer ABC meeting its SLA?") == []


def test_feedback_retrieval_is_workspace_scoped_and_never_uses_a_downvote_as_positive(system):
    s = system
    workspace_a = s.workspaces.create(WorkspaceCreate(name="Feedback scope A"), ADMIN)
    workspace_b = s.workspaces.create(WorkspaceCreate(name="Feedback scope B"), ADMIN)
    index = FakeIndexClient()

    good_trace = uuid4()
    _seed_trace(s, workspace_a, good_trace, question="What is the refund window?", answer="30 days from delivery.")
    FeedbackService(s.db, FakeLLM(0.0), index, top_k=5).submit(
        workspace_a.workspace_uuid, FeedbackRequest(trace_id=str(good_trace), rating="GOOD"), ADMIN
    )

    bad_trace = uuid4()
    _seed_trace(s, workspace_a, bad_trace, question="What is the refund window?", answer="Wrong answer entirely.")
    FeedbackService(s.db, FakeLLM(0.0), index, top_k=5).submit(
        workspace_a.workspace_uuid,
        FeedbackRequest(trace_id=str(bad_trace), rating="BAD", comment="This contradicts the approved policy"),
        ADMIN,
    )

    service = FeedbackService(s.db, FakeLLM(0.0), index, top_k=5)
    lessons_a = service.retrieve(workspace_a.workspace_uuid, "What is the refund window?")
    assert len(lessons_a) == 2
    ratings = {l["label"].split(" ")[0] for l in lessons_a}
    assert ratings == {"GOOD", "BAD"}
    for lesson in lessons_a:
        if lesson["label"].startswith("BAD"):
            assert lesson["example"] == "This contradicts the approved policy"
            assert "Wrong answer entirely." not in lesson["example"]

    lessons_b = service.retrieve(workspace_b.workspace_uuid, "What is the refund window?")
    assert lessons_b == []
