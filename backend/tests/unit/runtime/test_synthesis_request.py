from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from cce.runtime.compound import CompoundQuery
from cce.runtime.models import (
    AnswerResult, AtomicQueryResponse, QueryBranchResult, QueryRequest,
    SynthesisRequest, WorkspaceInfo,
)


def test_synthesis_uses_typed_request_and_only_successful_on_answers():
    workspace = WorkspaceInfo(workspace_uuid=uuid4(), workspace_id="ERP_workspace", name="ERP")
    atomic = AtomicQueryResponse(
        trace_id=uuid4(), question="How large is the product matrix?", workspace=workspace,
        context_on=QueryBranchResult(status="SUCCESS", answer="3,000 variants"),
        context_off=QueryBranchResult(status="SUCCESS", answer="Excluded OFF answer"),
    )
    runtime = Mock()

    def invoke(trace, task, instruction, request, output_type):
        assert isinstance(request, SynthesisRequest)
        assert [a.answer for a in request.successful_on_answers] == ["3,000 variants"]
        assert "Excluded OFF answer" not in request.model_dump_json()
        return AnswerResult(answer="3,000 variants")

    runtime._call.side_effect = invoke
    graph = CompoundQuery(runtime, Mock(), Mock(), Mock())
    result = graph._synthesize(dict(
        results=[(0, atomic)], trace_id=uuid4(), workspace=workspace,
        request=QueryRequest(question=atomic.question, workspace_id=workspace.workspace_id),
        package=SimpleNamespace(version=2, package_version_id=uuid4()),
        package_info={"name": "ERP"},
    ))
    assert result["response"].status == "SUCCESS"
    assert result["response"].answer == "3,000 variants"
