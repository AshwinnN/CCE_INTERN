from types import SimpleNamespace
from uuid import uuid4

from cce.config.settings import Settings
from cce.runtime.models import QueryIntent, SourceSchema, TableSchema, ColumnSchema
from cce.runtime.orchestrator import RuntimeOrchestrator, BranchWork


def setup_case(graph_fails=False):
    workspace, source = uuid4(), uuid4()
    hit = {'memory_id': 'source-memory', 'score': .9, 'chunk_text': 'The documented deadline is 48 hours.',
           'metadata': {'source_id': str(source), 'workspace_uuid': str(workspace)}}

    class Index:
        graph_calls = 0

        def search(self, *args, **kwargs):
            assert kwargs['metadata_filter']['workspace_uuid'] == str(workspace)
            return [hit]

        def graph(self, *args, **kwargs):
            self.graph_calls += 1
            if graph_fails:
                raise RuntimeError('graph unavailable')
            return {'entities': [
                {'entity_id': 'safe', 'name': 'Deadline', 'source_memories': ['source-memory']},
                {'entity_id': 'mixed', 'name': 'Mixed workspace', 'source_memories': ['source-memory', 'other-workspace']},
            ], 'relationships': [{'source_entity_id': 'safe', 'target_entity_id': 'mixed', 'relation_type': 'RELATED'}]}

    schema = SourceSchema(source_id=source, tables=[TableSchema(database='DB', schema_name='PUBLIC', name='ITEMS', columns=[ColumnSchema(name='ID', data_type='TEXT')])])
    traces = SimpleNamespace(workspace_source_ids=lambda d: [str(source)], node=lambda *a: None,
                             workspace_schemas=lambda d: [schema])
    index = Index()
    runtime = RuntimeOrchestrator(Settings(), None, None, None, traces, index, None)
    work = BranchWork(question='What is the reporting deadline?', trace_id=uuid4(), workspace_uuid=workspace,
                      intent=QueryIntent(intent='policy', needs_live_data=False), branch='ON')
    return runtime, work, index


def test_unapproved_source_evidence_and_scoped_graph_work_without_package():
    runtime, work, index = setup_case()
    work = runtime.retrieve_and_assemble(work)
    assert work.result is None
    assert work.context.package_id is None
    assert work.context.vector_hits[0].content == 'The documented deadline is 48 hours.'
    assert [e.entity_id for e in work.context.graph.entities] == ['safe']
    assert work.context.graph.relationships == []
    assert index.graph_calls == 1
    runtime.resolve_data_source(work)
    assert work.source is None  # policy answers do not require a database
    assert work.result is None


def test_live_question_still_resolves_structured_source_without_package():
    runtime, work, _ = setup_case()
    work.intent.needs_live_data = True
    work = runtime.retrieve_and_assemble(work)
    work = runtime.resolve_data_source(work)
    assert work.source.tables[0].name == 'ITEMS'
    assert work.result is None


def test_graph_failure_is_visible_without_discarding_vector_evidence():
    runtime, work, index = setup_case(graph_fails=True)
    work = runtime.retrieve_and_assemble(work)
    assert index.graph_calls == 1
    assert work.context.graph.status == 'UNAVAILABLE'
    assert 'AGENTICPLANE_GRAPH_UNAVAILABLE' in work.context.warnings
    assert work.context.vector_hits
