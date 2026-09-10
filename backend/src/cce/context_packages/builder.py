"""Deterministic package materialization. Caller holds the workspace lock/transaction."""

from uuid import uuid4

from cce.context_packages.models.assets import GovernedAsset, PackageSnapshot
from cce.context_packages.validator import validate_effective
from cce.governance.models import BuildResult
from cce.governance.policy import require_approved
from cce.persistence.postgres.lifecycle_db import json_param


def assert_assets_approved(assets):
    for asset in assets:
        require_approved(asset["status"])


class PackageBuilder:
    def __init__(self, context_repository, schema_lookup):
        self.context = context_repository
        self.schema_lookup = schema_lookup

    def build(self, batch, proposals, cur) -> BuildResult:
        bid = batch["proposal_batch_id"]
        workspace_uuid = batch["workspace_uuid"]
        if any(p.status == "PROPOSED" for p in proposals):
            return BuildResult(proposal_batch_id=bid, status="READY_FOR_REVIEW")
        approved = [p for p in proposals if p.status == "APPROVED"]
        if not approved:
            cur.execute(
                "UPDATE proposal_batch SET status='NO_CHANGE' WHERE proposal_batch_id=%s",
                (str(bid),),
            )
            return BuildResult(proposal_batch_id=bid, status="NO_CHANGE")
        old = self.context.active(workspace_uuid, cur)
        effective = {str(a.asset_id): a for a in old.assets} if old else {}
        changed = []
        retired = []
        errors = []
        for p in approved:
            target = str(p.target_asset_id) if p.target_asset_id else None
            if p.operation in ("UPDATE", "REMOVE") and target not in effective:
                errors.append(f"{p.proposal_id}: target is no longer active")
                continue
            if p.operation == "REMOVE":
                retired.append(target)
                del effective[target]
                continue
            if p.operation == "CREATE" and any(
                (a.payload.asset_type, a.payload.canonical_key)
                == (p.reviewed_payload.asset_type, p.reviewed_payload.canonical_key)
                for a in effective.values()
            ):
                errors.append(f"{p.proposal_id}: CREATE conflicts with active identity")
                continue
            asset_id = target or str(uuid4())
            revision_no = effective[target].revision_no + 1 if target else 1
            if not target:
                cur.execute(
                    "SELECT asset_id::text FROM context_asset WHERE workspace_uuid=%s AND asset_type=%s AND canonical_key=%s AND NOT is_active",
                    (
                        str(workspace_uuid),
                        p.reviewed_payload.asset_type,
                        p.reviewed_payload.canonical_key,
                    ),
                )
                retired_asset = cur.fetchone()
                if retired_asset:
                    asset_id = retired_asset["asset_id"]
                    cur.execute(
                        "SELECT max(revision_no) n FROM context_asset_revision WHERE asset_id=%s",
                        (asset_id,),
                    )
                    revision_no = cur.fetchone()["n"] + 1
            asset = GovernedAsset(
                asset_id=asset_id,
                asset_revision_id=uuid4(),
                workspace_uuid=workspace_uuid,
                revision_no=revision_no,
                payload=p.reviewed_payload,
                evidence=p.evidence,
                approved_by=p.resolved_by,
            )
            effective[asset_id] = asset
            changed.append((p, asset))
        errors.extend(validate_effective(list(effective.values()), self.schema_lookup))
        if errors:
            cur.execute(
                "UPDATE proposal_batch SET status='BUILD_BLOCKED',validation_errors=%s WHERE proposal_batch_id=%s",
                (json_param(errors), str(bid)),
            )
            return BuildResult(
                proposal_batch_id=bid, status="BUILD_BLOCKED", validation_errors=errors
            )
        cur.execute("SELECT package_id FROM context_package WHERE workspace_uuid=%s FOR UPDATE", (str(workspace_uuid),))
        package_id = cur.fetchone()["package_id"]
        snapshot = PackageSnapshot(
            package_id=package_id,
            workspace_uuid=workspace_uuid,
            package_version_id=uuid4(),
            version=old.version + 1 if old else 1,
            assets=list(effective.values()),
        )
        for p, a in changed:
            if p.operation == "CREATE":
                cur.execute(
                    "INSERT INTO context_asset(asset_id,workspace_uuid,asset_type,canonical_key) VALUES(%s,%s,%s,%s) ON CONFLICT(asset_id) DO UPDATE SET is_active=true,retired_at=NULL",
                    (
                        str(a.asset_id),
                        str(workspace_uuid),
                        a.payload.asset_type,
                        a.payload.canonical_key,
                    ),
                )
            cur.execute(
                "INSERT INTO context_asset_revision(asset_revision_id,asset_id,revision_no,payload,created_from_proposal_id) VALUES(%s,%s,%s,%s,%s)",
                (
                    str(a.asset_revision_id),
                    str(a.asset_id),
                    a.revision_no,
                    json_param(a.payload),
                    str(p.proposal_id),
                ),
            )
            for e in a.evidence:
                cur.execute(
                    "INSERT INTO asset_revision_evidence VALUES(%s,%s)",
                    (str(a.asset_revision_id), str(e.evidence_id)),
                )
        for asset_id in retired:
            cur.execute(
                "UPDATE context_asset SET is_active=false,retired_at=now() WHERE asset_id=%s",
                (asset_id,),
            )
        # Project exact revisions; historical graph rows remain addressable by old manifests.
        entity_ids = {}
        for a in snapshot.assets:
            if a.payload.asset_type == "ENTITY":
                cur.execute(
                    """INSERT INTO graph_entity(entity_id,workspace_uuid,canonical_key,entity_type,asset_revision_id)
                    VALUES(%s,%s,%s,%s,%s) ON CONFLICT(asset_revision_id) DO NOTHING""",
                    (
                        str(uuid4()),
                        str(workspace_uuid),
                        a.payload.canonical_key,
                        a.payload.entity_type,
                        str(a.asset_revision_id),
                    ),
                )
                cur.execute(
                    "SELECT entity_id::text FROM graph_entity WHERE asset_revision_id=%s",
                    (str(a.asset_revision_id),),
                )
                entity_ids[a.payload.canonical_key] = cur.fetchone()["entity_id"]
        for a in snapshot.assets:
            if a.payload.asset_type == "RELATIONSHIP":
                cur.execute(
                    """INSERT INTO graph_edge(edge_id,workspace_uuid,from_entity_id,to_entity_id,relation_type,asset_revision_id)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (
                        str(uuid4()),
                        str(workspace_uuid),
                        entity_ids[a.payload.from_entity],
                        entity_ids[a.payload.to_entity],
                        a.payload.relation_type,
                        str(a.asset_revision_id),
                    ),
                )
        cur.execute(
            "UPDATE package_version SET status='SUPERSEDED' WHERE package_id=%s AND status='ACTIVE'",
            (str(package_id),),
        )
        cur.execute(
            "INSERT INTO package_version(package_version_id,package_id,version_no,status,created_from_proposal_batch_id) VALUES(%s,%s,%s,%s,%s)",
            (
                str(snapshot.package_version_id),
                str(package_id),
                snapshot.version,
                "ACTIVE",
                str(bid),
            ),
        )
        for a in snapshot.assets:
            cur.execute(
                "INSERT INTO package_asset VALUES(%s,%s)",
                (str(snapshot.package_version_id), str(a.asset_revision_id)),
            )
        cur.execute(
            "INSERT INTO package_snapshot(package_version_id,payload) VALUES(%s,%s)",
            (str(snapshot.package_version_id), json_param(snapshot)),
        )
        cur.execute(
            "UPDATE proposal_batch SET status='PACKAGED',packaged_at=now() WHERE proposal_batch_id=%s",
            (str(bid),),
        )
        return BuildResult(
            proposal_batch_id=bid,
            status="PACKAGED",
            package_version_id=snapshot.package_version_id,
        )
