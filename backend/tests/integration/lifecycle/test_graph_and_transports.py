from types import SimpleNamespace

import pytest
from cce.context_packages.models.assets import Entity, Relationship
from cce.context_packages.service import ContextPackageService
from cce.gen.cce.v1 import governance_pb2, packages_pb2
from cce.governance.service import GovernanceService
from cce.http.app import create_app
from cce.rpc.services.governance_service import GovernanceRPCService
from cce.rpc.services.package_service import PackageRPCService
from fastapi.testclient import TestClient
from test_lifecycle import STEWARD, candidate, finish, setup_source, start


def test_relational_graph_depth_and_http_grpc_parity(system):
    s = system
    domain, source = setup_source(s)
    run, job, items = start(s, source)
    candidates = [
        candidate(
            domain,
            items[0],
            run,
            Entity(canonical_key=f"e{i}", name=f"Entity {i}", entity_type="record"),
        )
        for i in range(4)
    ]
    candidates += [
        candidate(
            domain,
            items[0],
            run,
            Relationship(
                canonical_key=f"r{i}",
                from_entity=f"e{i}",
                to_entity=f"e{i + 1}",
                relation_type="links",
            ),
        )
        for i in range(3)
    ]
    finish(s, job, items, [candidates])
    batch = s.governance.promote(run.ingestion_run_id, domain.domain_id)
    app = SimpleNamespace(
        governance_service=GovernanceService(s.governance),
        package_service=ContextPackageService(s.context),
        domain_repository=s.domains,
        ready=True,
    )
    client = TestClient(create_app(app))
    proposals = client.get(
        "/proposals", params={"domain_id": str(domain.domain_id)}
    ).json()["proposals"]
    assert len(proposals) == 7
    assert (
        client.post(
            "/proposals/" + proposals[0]["proposal_id"] + "/approve",
            json={"actor": {"actor_id": "reader", "roles": ["QUERY_CONSUMER"]}},
        ).status_code
        == 403
    )
    rpc = GovernanceRPCService(app)
    grpc_list = rpc.ListProposals(
        governance_pb2.ListProposalsRequest(domain_id=str(domain.domain_id)), None
    )
    assert len(grpc_list.proposals) == 7 and grpc_list.proposals[0].reviewed_payload
    for p in proposals:
        response = client.post(
            "/proposals/" + p["proposal_id"] + "/approve",
            json={"actor": STEWARD.model_dump()},
        )
        assert response.status_code == 200, response.text
    package = s.context.active(domain.domain_id)
    seed = next(a for a in package.assets if a.payload.canonical_key == "e0")
    expanded = s.context.expand(package, [seed], 2)
    assert {
        a.payload.canonical_key for a in expanded if a.payload.asset_type == "ENTITY"
    } == {"e0", "e1", "e2"}
    proto = PackageRPCService(app).GetActivePackage(
        packages_pb2.GetActivePackageRequest(domain_id=str(domain.domain_id)), None
    )
    assert len(proto.assets) == 7 and proto.snapshot["version"] == 1
    # Resolved proposals and machine payload cannot be mutated, including via DB.
    with pytest.raises(Exception):
        with s.db.transaction() as cur:
            cur.execute("UPDATE context_asset_revision SET payload='{}'::jsonb")


def test_lease_expiry_reclaims_same_run_and_fences_old_worker(system):
    s = system
    domain, source = setup_source(s)
    run = s.ingestion.create_or_resume(source)
    first = s.jobs.claim()
    with s.db.transaction() as cur:
        cur.execute("UPDATE cce_job SET lease_until=now()-interval '1 second'")
    s.jobs.finish(first, "expired worker before reclaim")
    assert s.ingestion.get(run.ingestion_run_id).status == "RUNNING"
    second = s.jobs.claim()
    assert (
        second.ingestion_run_id == first.ingestion_run_id
        and second.claim_token != first.claim_token
    )
    with pytest.raises(RuntimeError):
        s.ingestion.inventory(first, [])
    assert s.jobs.renew(first) is False and s.jobs.renew(second) is True
    s.jobs.finish(first, "stale worker")
    assert s.ingestion.get(run.ingestion_run_id).status == "RUNNING"
