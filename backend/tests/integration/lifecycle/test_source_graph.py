from uuid import uuid4

from cce.config.settings import Settings
from cce.context_packages.models.assets import Evidence, Glossary
from cce.governance.models import Candidate, ExtractionResult, ProposalFilter
from cce.ingestion.lifecycle_models import GroundedItem, SourceItem
from cce.ingestion.source_graph import SourceGraph
from test_lifecycle import setup_source


class Grounding:
    def __init__(self, source):
        self.source = source
        self.fail = True
        self.hashes = ["a", "a"]
        self.processed = []

    def discover(self, source):
        return [
            SourceItem(
                source_item_id=uuid4(),
                source_id=source,
                source_native_id=str(i),
                canonical_uri="file:///" + str(i),
                content_hash=h,
                change_type="NEW",
            )
            for i, h in enumerate(self.hashes)
        ]

    def ground(self, item, run):
        self.processed.append(item.source_native_id)
        if self.fail and item.source_native_id == "1":
            raise RuntimeError("Temporary failure")
        from cce.ingestion.lifecycle_models import GroundingPayload, IndexBlock

        return GroundedItem(
            content="Definition evidence",
            payload=GroundingPayload(
                document_id=item.source_native_id,
                source_id=item.source_id,
                source_ref=item.canonical_uri,
                object_id=item.source_native_id,
                revision=item.content_hash,
                trace_id=run,
                blocks=[IndexBlock(id="e1", text="Definition evidence")],
            ),
        )


class Index:
    def __init__(self):
        self.indexed = []

    def index(self, payload):
        self.indexed.append(payload)

    def search(self, *args, metadata_filter, **kwargs):
        return [
            {
                "memory_id": str(uuid4()),
                "score": 0.95,
                "chunk_text": "Definition evidence",
                "metadata": metadata_filter,
            }
        ]


class LLM:
    def __init__(self, workspace):
        self.workspace = workspace

    def invoke(self, task, instruction, request, output):
        item = request.source_item
        hit = request.evidence[0]
        return ExtractionResult(
            candidates=[
                Candidate(
                    workspace_uuid=self.workspace.workspace_uuid,
                    payload=Glossary(
                        canonical_key="term", term="Term", definition="Definition"
                    ),
                    evidence=[
                        Evidence(
                            source_id=item.source_id,
                            source_item_id=item.source_item_id,
                            source_uri=item.canonical_uri,
                            document_id=item.source_native_id,
                            agentic_memory_id=hit.memory_id,
                            ingestion_run_id=hit.metadata["ingestion_run_id"],
                            content_hash=item.content_hash,
                        )
                    ],
                )
            ]
        )


def test_source_fanout_partial_resume_changed_again_and_promotion(system):
    s = system
    workspace, source = setup_source(s)
    ground = Grounding(source)
    index = Index()
    graph = SourceGraph(
        Settings(),
        s.ingestion,
        s.workspaces,
        s.context,
        s.governance,
        ground,
        index,
        LLM(workspace),
    )
    run = s.ingestion.create_or_resume(source)
    job = s.jobs.claim()
    assert graph.run(job).status == "PARTIAL"
    s.jobs.finish(job)
    assert not s.governance.list(ProposalFilter(workspace_uuid=s.workspace_uuid))
    ground.fail = False
    ground.hashes[0] = "b"
    resumed = s.ingestion.create_or_resume(source)
    assert resumed.ingestion_run_id == run.ingestion_run_id
    job = s.jobs.claim()
    assert graph.run(job).status == "SUCCESS"
    s.jobs.finish(job)
    assert ground.processed.count("0") == 2  # successful but changed again -> reprocess
    assert len(s.governance.list(ProposalFilter(workspace_uuid=s.workspace_uuid))) == 1
    assert len(s.governance.list(ProposalFilter(workspace_uuid=s.workspace_uuid))[0].evidence) == 2
    assert all(
        p["metadata"]["workspace_uuid"] == str(workspace.workspace_uuid) for p in index.indexed
    )


def test_real_local_grounding_redacts_before_workspace_detection(tmp_path):
    from cce.sources.service import SourceService
    from cce.ingestion.grounding import GroundingAdapter
    from types import SimpleNamespace

    source = uuid4()
    path = tmp_path / "contract.txt"
    path.write_text(
        "Approved threshold is 80%. Contact steward@example.com. SSN 123-45-6789."
    )
    service = SourceService(
        source_repository=SimpleNamespace(
            get_internal_source=lambda _: {
                "source_id": str(source),
                "source_type": "local-fs",
                "kind": "unstructured",
                "enabled": True,
                "config": {"root_path": str(tmp_path)},
            }
        ),
        metadata_repository=None,
        checkpoint_store=None,
        index_client=None,
        ingestion_repository=None,
    )
    ground = GroundingAdapter(service)
    items = ground.discover(source)
    assert len(items) == 1
    item = ground.ground(items[0], uuid4())
    assert (
        "steward@example.com" not in item.content and "123-45-6789" not in item.content
    )
    assert "80%" in item.content
    assert "[REDACTED_EMAIL]" in item.content
    assert item.payload.source_id == source
