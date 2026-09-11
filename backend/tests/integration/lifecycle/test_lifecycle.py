from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from cce.context_packages.models.assets import (
    Evidence,
    Glossary,
    Relationship,
)
from cce.governance.models import (
    Actor,
    Candidate,
    DomainCreate,
    ProposalFilter,
    ReviewRequest,
)
from cce.ingestion.lifecycle_models import ItemResult, SourceItem

STEWARD = Actor(actor_id="steward", roles=["STEWARD"])
ADMIN = Actor(actor_id="admin", roles=["ADMIN"])


def setup_source(s):
    domain = s.domains.create(DomainCreate(name="Test domain"), ADMIN)
    source = uuid4()
    with s.db.transaction() as cur:
        cur.execute(
            "INSERT INTO cce_source(source_id,adapter,account_id,kind) VALUES(%s,'local-fs',%s,'unstructured')",
            (str(source), str(source)),
        )
    return domain, source


def start(s, source, n=1, hash="a"):
    run = s.ingestion.create_or_resume(source)
    job = s.jobs.claim()
    items = [
        SourceItem(
            source_item_id=uuid4(),
            source_id=source,
            source_native_id=f"doc{i}",
            canonical_uri=f"file:///doc{i}",
            content_hash=hash,
            change_type="NEW",
        )
        for i in range(n)
    ]
    inventory = s.ingestion.inventory(job, items)
    return run, job, inventory.items


def evidence(item, run, memory=None):
    return Evidence(
        source_id=item.source_id,
        source_item_id=item.source_item_id,
        source_uri=item.canonical_uri,
        document_id=item.source_native_id,
        ingestion_run_id=run.ingestion_run_id,
        content_hash=item.content_hash,
        agentic_memory_id=memory or str(uuid4()),
    )


def candidate(domain, item, run, payload=None):
    return Candidate(
        domain_id=domain.domain_id,
        payload=payload
        or Glossary(canonical_key="term", term="Term", definition="Definition"),
        evidence=[evidence(item, run)],
    )


def finish(s, job, items, candidates):
    results = []
    for i, item in enumerate(items):
        result = ItemResult(item=item, status="SUCCESS")
        s.ingestion.save_result(job, result, candidates[i])
        results.append(result)
    s.ingestion.finish(job, results)
    s.jobs.finish(job)


def approve_all(s, batch):
    proposals = s.governance.list(
        ProposalFilter(proposal_batch_id=batch.proposal_batch_id)
    )
    for p in proposals:
        s.governance.review(
            ReviewRequest(proposal_id=p.proposal_id, actor=STEWARD), "APPROVE"
        )
    return proposals


def test_partial_resume_dedupe_no_change_and_missing_evidence(system):
    s = system
    domain, source = setup_source(s)
    run, job, items = start(s, source, 2)
    c0 = candidate(domain, items[0], run)
    c1 = candidate(domain, items[1], run)
    success = ItemResult(item=items[0], status="SUCCESS")
    failure = ItemResult(item=items[1], status="FAILED", error="provider unavailable")
    s.ingestion.save_result(job, success, [c0])
    s.ingestion.save_result(job, failure, [])
    assert s.ingestion.finish(job, [success, failure]).status == "PARTIAL"
    s.jobs.finish(job)
    assert not s.governance.list(ProposalFilter())
    with pytest.raises(ValueError):
        s.governance.promote(run.ingestion_run_id, domain.domain_id)
    assert s.context.active(domain.domain_id) is None
    resumed, job, retry = start(s, source, 2)
    assert resumed.ingestion_run_id == run.ingestion_run_id
    assert retry[0].change_type == "UNCHANGED" and retry[1].change_type == "CHANGED"
    finish(s, job, retry, [[], [c1]])
    batch = s.governance.promote(run.ingestion_run_id, domain.domain_id)
    proposals = s.governance.list(ProposalFilter())
    assert len(proposals) == 1 and len(proposals[0].evidence) == 2
    approve_all(s, batch)
    v1 = s.context.active(domain.domain_id)
    assert v1.version == 1
    # Both support sources remain attached; losing one cannot remove the asset.
    with s.db.transaction() as cur:
        cur.execute(
            "UPDATE source_item SET availability_status='MISSING' WHERE source_item_id=%s",
            (str(items[0].source_item_id),),
        )
    assert not s.ingestion.missing_candidates(items[0])
    run2, job2, items2 = start(s, source, 2, hash="b")
    same = candidate(domain, items2[0], run2)
    finish(s, job2, items2, [[same], []])
    unchanged = s.governance.promote(run2.ingestion_run_id, domain.domain_id)
    assert unchanged.status == "NO_CHANGE"
    assert s.context.active(domain.domain_id).version == 1
    # Current evidence links allow new memory hits without changing approved semantic payload.
    assert s.context.linked_assets(v1, [same.evidence[0].agentic_memory_id])


def test_batch_terminal_gate_full_snapshot_remove_history_and_atomic_activation(system):
    s = system
    domain, source = setup_source(s)
    run, job, items = start(s, source)
    a = candidate(domain, items[0], run)
    b = candidate(
        domain,
        items[0],
        run,
        Glossary(canonical_key="other", term="Other", definition="Other definition"),
    )
    finish(s, job, items, [[a, b]])
    batch = s.governance.promote(run.ingestion_run_id, domain.domain_id)
    proposals = s.governance.list(ProposalFilter())
    s.governance.review(
        ReviewRequest(proposal_id=proposals[0].proposal_id, actor=STEWARD), "APPROVE"
    )
    assert s.context.active(domain.domain_id) is None
    s.governance.review(
        ReviewRequest(proposal_id=proposals[1].proposal_id, actor=STEWARD), "APPROVE"
    )
    v1 = s.context.active(domain.domain_id)
    assert len(v1.assets) == 2
    run2, job2, items2 = start(s, source, hash="b")
    c = candidate(
        domain,
        items2[0],
        run2,
        Glossary(canonical_key="third", term="Third", definition="Third definition"),
    )
    finish(s, job2, items2, [[c]])
    batch2 = s.governance.promote(run2.ingestion_run_id, domain.domain_id)
    approve_all(s, batch2)
    v2 = s.context.active(domain.domain_id)
    assert v2.version == 2 and len(v2.assets) == 3
    run3, job3, missing = start(s, source, n=0)
    removals = s.ingestion.missing_candidates(missing[0])
    assert len(removals) == 3
    finish(s, job3, missing, [removals])
    batch3 = s.governance.promote(run3.ingestion_run_id, domain.domain_id)
    assert s.context.active(domain.domain_id).version == 2
    approve_all(s, batch3)
    assert not s.context.active(domain.domain_id).assets
    assert len(s.context.version(v1.package_id, 1).assets) == 2
    with s.db.transaction() as cur:
        cur.execute("SELECT count(*) n FROM package_version WHERE status='ACTIVE'")
        assert cur.fetchone()["n"] == 1
        cur.execute("SELECT count(*) n FROM context_asset WHERE is_active")
        assert cur.fetchone()["n"] == 0
        cur.execute("SELECT count(*) n FROM context_asset_revision")
        assert cur.fetchone()["n"] == 3


def test_conflict_edit_audit_blocked_all_rejected_and_concurrent_run(system):
    s = system
    domain, source = setup_source(s)
    with ThreadPoolExecutor(4) as pool:
        runs = list(pool.map(lambda _: s.ingestion.create_or_resume(source), range(4)))
    assert len({r.ingestion_run_id for r in runs}) == 1
    run, job, items = start(s, source, 2)
    a = candidate(domain, items[0], run)
    b = candidate(
        domain,
        items[1],
        run,
        Glossary(
            canonical_key="term", term="Term", definition="Conflicting definition"
        ),
    )
    finish(s, job, items, [[a], [b]])
    batch = s.governance.promote(run.ingestion_run_id, domain.domain_id)
    p = s.governance.list(ProposalFilter())[0]
    assert p.reviewed_payload.asset_type == "AMBIGUITY"
    edited = p.reviewed_payload.model_copy(
        update={"resolution": "Steward-selected definition"}
    )
    s.governance.review(
        ReviewRequest(proposal_id=p.proposal_id, actor=STEWARD, payload=edited), "EDIT"
    )
    assert s.governance.get(p.proposal_id).machine_payload.resolution is None
    approve_all(s, batch)
    v1 = s.context.active(domain.domain_id)
    run2, job2, items2 = start(s, source, 2, hash="b")
    broken = candidate(
        domain,
        items2[0],
        run2,
        Relationship(
            canonical_key="broken",
            from_entity="absent",
            to_entity="missing",
            relation_type="links",
        ),
    )
    finish(s, job2, items2, [[broken], []])
    batch2 = s.governance.promote(run2.ingestion_run_id, domain.domain_id)
    approve_all(s, batch2)
    assert s.context.active(domain.domain_id).version == v1.version
    with s.db.transaction() as cur:
        cur.execute(
            "SELECT status,validation_errors FROM proposal_batch WHERE proposal_batch_id=%s",
            (str(batch2.proposal_batch_id),),
        )
        row = cur.fetchone()
        assert row["status"] == "BUILD_BLOCKED" and row["validation_errors"]
    run3, job3, items3 = start(s, source, 2, hash="c")
    finish(s, job3, items3, [[candidate(domain, items3[0], run3)], []])
    batch3 = s.governance.promote(run3.ingestion_run_id, domain.domain_id)
    for p in s.governance.list(
        ProposalFilter(proposal_batch_id=batch3.proposal_batch_id)
    ):
        s.governance.review(
            ReviewRequest(proposal_id=p.proposal_id, actor=STEWARD), "REJECT"
        )
    assert s.context.active(domain.domain_id).version == v1.version
