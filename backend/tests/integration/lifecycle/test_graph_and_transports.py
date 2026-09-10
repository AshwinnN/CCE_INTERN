from types import SimpleNamespace

import pytest
from google.protobuf.json_format import MessageToDict
from cce.context_packages.models.assets import Entity, Relationship
from cce.context_packages.service import ContextPackageService
from cce.gen.cce.v1 import workspaces_pb2
from cce.governance.service import GovernanceService
from cce.http.app import create_app
from cce.rpc.services.workspace_service import WorkspaceRPCService
from fastapi.testclient import TestClient
from test_lifecycle import STEWARD, candidate, finish, setup_source, start


def test_relational_graph_depth_and_http_grpc_parity(system):
    s = system
    workspace, source = setup_source(s)
    run, job, items = start(s, source)
    candidates = [
        candidate(
            workspace,
            items[0],
            run,
            Entity(canonical_key=f"e{i}", name=f"Entity {i}", entity_type="record"),
        )
        for i in range(4)
    ]
    candidates += [
        candidate(
            workspace,
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
    batch = s.governance.promote(run.ingestion_run_id, workspace.workspace_uuid)
    app = SimpleNamespace(
        governance_service=GovernanceService(s.governance),
        package_service=ContextPackageService(s.context),
        workspace_repository=s.workspaces,
        ready=True,
    )
    client = TestClient(create_app(app))
    scope = "/workspaces/" + workspace.workspace_id
    proposals = client.get(scope + "/proposals").json()
    assert len(proposals) == 7
    assert (
        client.post(
            scope + "/proposals/" + proposals[0]["proposal_id"] + "/approve",
            json={"actor": {"actor_id": "reader", "roles": ["QUERY_CONSUMER"]}},
        ).status_code
        == 403
    )
    rpc = WorkspaceRPCService(app)
    grpc_list = rpc.ListProposals(
        workspaces_pb2.WorkspaceRequest(workspace_id=workspace.workspace_id), None
    )
    grpc_proposals = MessageToDict(grpc_list.data)
    assert len(grpc_proposals) == 7 and grpc_proposals[0]["reviewed_payload"]
    for p in proposals:
        response = client.post(
            scope + "/proposals/" + p["proposal_id"] + "/approve",
            json={"actor": STEWARD.model_dump()},
        )
        assert response.status_code == 200, response.text
    package = s.context.active(workspace.workspace_uuid)
    seed = next(a for a in package.assets if a.payload.canonical_key == "e0")
    expanded = s.context.expand(package, [seed], 2)
    assert {
        a.payload.canonical_key for a in expanded if a.payload.asset_type == "ENTITY"
    } == {"e0", "e1", "e2"}
    grpc_version = rpc.GetVersion(
        workspaces_pb2.WorkspaceRequest(workspace_id=workspace.workspace_id, resource_id="1"),
        None,
    )
    version_data = MessageToDict(grpc_version.data)
    assert len(version_data["assets"]) == 7 and version_data["version"] == 1
    http_version = client.get(scope + "/package/versions/1").json()
    assert len(http_version["assets"]) == 7 and http_version["version"] == 1
    # Resolved proposals and machine payload cannot be mutated, including via DB.
    with pytest.raises(Exception):
        with s.db.transaction() as cur:
            cur.execute("UPDATE context_asset_revision SET payload='{}'::jsonb")


def test_lease_expiry_reclaims_same_run_and_fences_old_worker(system):
    s = system
    workspace, source = setup_source(s)
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
