import hashlib
import json
from collections import defaultdict
from uuid import uuid4

from cce.context_packages.models.assets import Ambiguity, Evidence, asset_adapter
from cce.governance.models import (
    BuildResult,
    Candidate,
    Proposal,
    ProposalFilter,
    ReviewRequest,
)
from cce.persistence.postgres.lifecycle_db import json_param


def semantic_hash(payload):
    data = payload.model_dump(mode="json", exclude={"metadata"})
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class GovernanceRepository:
    def __init__(self, db, context, builder):
        self.db = db
        self.context = context
        self.builder = builder

    def _load(self, cur, row) -> Proposal:
        cur.execute(
            """SELECT e.* FROM proposal_evidence pe JOIN context_evidence e USING(evidence_id)
            WHERE pe.proposal_id=%s""",
            (str(row["proposal_id"]),),
        )
        evidence = [Evidence.model_validate(dict(r)) for r in cur.fetchall()]
        return Proposal(
            proposal_id=row["proposal_id"],
            proposal_batch_id=row["proposal_batch_id"],
            workspace_uuid=row["workspace_uuid"],
            operation=row["operation"],
            target_asset_id=row["target_asset_id"],
            machine_payload=row["machine_payload"],
            reviewed_payload=row["reviewed_payload"],
            status=row["status"],
            evidence=evidence,
            resolved_by=row["resolved_by"],
            resolved_at=str(row["resolved_at"]) if row["resolved_at"] else None,
        )

    def list(self, filters: ProposalFilter) -> list[Proposal]:
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT p.*,b.workspace_uuid FROM proposal p JOIN proposal_batch b USING(proposal_batch_id)
                WHERE (%s IS NULL OR p.status=%s) AND (%s IS NULL OR b.workspace_uuid::text=%s)
                AND (%s IS NULL OR b.proposal_batch_id::text=%s) ORDER BY p.created_at,p.proposal_id""",
                (
                    filters.status,
                    filters.status,
                    str(filters.workspace_uuid) if filters.workspace_uuid else None,
                    str(filters.workspace_uuid) if filters.workspace_uuid else None,
                    str(filters.proposal_batch_id)
                    if filters.proposal_batch_id
                    else None,
                    str(filters.proposal_batch_id)
                    if filters.proposal_batch_id
                    else None,
                ),
            )
            return [self._load(cur, r) for r in cur.fetchall()]

    def get(self, proposal_id, workspace_uuid) -> Proposal:
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT p.*,b.workspace_uuid FROM proposal p JOIN proposal_batch b USING(proposal_batch_id) WHERE proposal_id=%s AND b.workspace_uuid=%s",
                (str(proposal_id),str(workspace_uuid)),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("Proposal not found")
            return self._load(cur, row)

    def review(self, request: ReviewRequest, action: str) -> Proposal:
        request.actor.require("STEWARD")
        with self.db.transaction() as cur:
            # Consistent workspace -> batch -> proposal lock order across build/review/promotion.
            cur.execute(
                "SELECT b.workspace_uuid FROM proposal p JOIN proposal_batch b USING(proposal_batch_id) WHERE p.proposal_id=%s AND b.workspace_uuid=%s",
                (str(request.proposal_id),str(request.workspace_uuid)),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("Proposal not found")
            cur.execute(
                "SELECT workspace_uuid FROM workspace WHERE workspace_uuid=%s FOR UPDATE",
                (str(row["workspace_uuid"]),),
            )
            cur.execute(
                "SELECT p.*,b.workspace_uuid FROM proposal p JOIN proposal_batch b USING(proposal_batch_id) WHERE proposal_id=%s FOR UPDATE OF p,b",
                (str(request.proposal_id),),
            )
            row = cur.fetchone()
            proposal = self._load(cur, row)
            if proposal.status != "PROPOSED":
                raise ValueError(
                    "Resolved proposals cannot be changed; create a corrective proposal"
                )
            payload = request.payload if action == "EDIT" else proposal.reviewed_payload
            if payload is None:
                raise ValueError("An edited payload is required")
            payload = asset_adapter.validate_python(payload.model_dump())
            if (payload.asset_type, payload.canonical_key) != (
                proposal.machine_payload.asset_type,
                proposal.machine_payload.canonical_key,
            ):
                raise ValueError("Review cannot change asset identity")
            cur.execute(
                "INSERT INTO proposal_review_action(action_id,proposal_id,actor_id,action,previous_payload,new_payload,comment) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (
                    str(uuid4()),
                    str(request.proposal_id),
                    request.actor.actor_id,
                    action,
                    json_param(proposal.reviewed_payload),
                    json_param(payload),
                    request.comment,
                ),
            )
            if action == "EDIT":
                cur.execute(
                    "UPDATE proposal SET reviewed_payload=%s WHERE proposal_id=%s",
                    (json_param(payload), str(request.proposal_id)),
                )
            else:
                cur.execute(
                    "UPDATE proposal SET status=%s,resolved_at=now(),resolved_by=%s WHERE proposal_id=%s",
                    (
                        "APPROVED" if action == "APPROVE" else "REJECTED",
                        request.actor.actor_id,
                        str(request.proposal_id),
                    ),
                )
                cur.execute(
                    "SELECT * FROM proposal_batch WHERE proposal_batch_id=%s",
                    (str(proposal.proposal_batch_id),),
                )
                batch = cur.fetchone()
                cur.execute(
                    "SELECT p.*,%s::uuid workspace_uuid FROM proposal p WHERE proposal_batch_id=%s",
                    (str(proposal.workspace_uuid), str(proposal.proposal_batch_id)),
                )
                proposals = [self._load(cur, r) for r in cur.fetchall()]
                self.builder.build(batch, proposals, cur)
        return self.get(request.proposal_id,request.workspace_uuid)

    def promote(self, run_id, workspace_uuid) -> BuildResult:
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT workspace_uuid FROM workspace WHERE workspace_uuid=%s FOR UPDATE",
                (str(workspace_uuid),),
            )
            cur.execute(
                "SELECT status FROM cce_ingestion_run WHERE run_id=%s FOR SHARE",
                (str(run_id),),
            )
            if cur.fetchone()["status"] != "SUCCESS":
                raise ValueError("Only SUCCESS ingestion can expose proposals")
            cur.execute(
                "SELECT proposal_batch_id,status,validation_errors FROM proposal_batch WHERE ingestion_run_id=%s AND workspace_uuid=%s",
                (str(run_id), str(workspace_uuid)),
            )
            existing = cur.fetchone()
            if existing:
                return BuildResult.model_validate(dict(existing))
            cur.execute(
                "SELECT payload FROM candidate_extraction WHERE ingestion_run_id=%s AND workspace_uuid=%s",
                (str(run_id), str(workspace_uuid)),
            )
            candidates = [
                Candidate.model_validate(r["payload"]) for r in cur.fetchall()
            ]
            grouped = defaultdict(list)
            for c in candidates:
                grouped[(c.payload.asset_type, c.payload.canonical_key)].append(c)
            active = self.context.active(workspace_uuid, cur)
            assets = (
                {
                    (a.payload.asset_type, a.payload.canonical_key): a
                    for a in active.assets
                }
                if active
                else {}
            )
            resolved = []
            for identity, group in grouped.items():
                variants = defaultdict(list)
                for c in group:
                    variants[(c.operation, semantic_hash(c.payload))].append(c)
                evidence = list(
                    {str(e.evidence_id): e for c in group for e in c.evidence}.values()
                )
                if len(variants) > 1:
                    payload = Ambiguity(
                        canonical_key="conflict:" + ":".join(identity),
                        description="Conflicting source facts require steward resolution",
                        alternatives=[
                            c.payload.model_dump_json()
                            for c in [v[0] for v in variants.values()]
                        ],
                    )
                    candidate = Candidate(
                        workspace_uuid=workspace_uuid, payload=payload, evidence=evidence
                    )
                    identity = ("AMBIGUITY", payload.canonical_key)
                else:
                    candidate = group[0].model_copy(update={"evidence": evidence})
                old = assets.get(identity)
                if candidate.operation == "REMOVE":
                    if old:
                        resolved.append(
                            candidate.model_copy(
                                update={"target_asset_id": old.asset_id}
                            )
                        )
                    continue
                if old and semantic_hash(old.payload) == semantic_hash(
                    candidate.payload
                ):
                    # Additional support is durable without changing immutable revision payloads.
                    for e in evidence:
                        self._evidence(cur, e)
                        cur.execute(
                            "INSERT INTO asset_revision_evidence VALUES(%s,%s) ON CONFLICT DO NOTHING",
                            (str(old.asset_revision_id), str(e.evidence_id)),
                        )
                    continue
                resolved.append(
                    candidate.model_copy(
                        update={
                            "operation": "UPDATE" if old else "CREATE",
                            "target_asset_id": old.asset_id if old else None,
                        }
                    )
                )
            bid = uuid4()
            status = "READY_FOR_REVIEW" if resolved else "NO_CHANGE"
            cur.execute(
                "INSERT INTO proposal_batch(proposal_batch_id,ingestion_run_id,workspace_uuid,status,proposal_count) VALUES(%s,%s,%s,%s,%s)",
                (str(bid), str(run_id), str(workspace_uuid), status, len(resolved)),
            )
            for c in resolved:
                pid = uuid4()
                cur.execute(
                    """INSERT INTO proposal(proposal_id,proposal_batch_id,operation,target_asset_id,asset_type,canonical_key,machine_payload,reviewed_payload)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        str(pid),
                        str(bid),
                        c.operation,
                        str(c.target_asset_id) if c.target_asset_id else None,
                        c.payload.asset_type,
                        c.payload.canonical_key,
                        json_param(c.payload),
                        json_param(c.payload),
                    ),
                )
                for e in c.evidence:
                    self._evidence(cur, e)
                    cur.execute(
                        "INSERT INTO proposal_evidence VALUES(%s,%s) ON CONFLICT DO NOTHING",
                        (str(pid), str(e.evidence_id)),
                    )
            return BuildResult(proposal_batch_id=bid, status=status)

    @staticmethod
    def _evidence(cur, e):
        cur.execute(
            """INSERT INTO context_evidence(evidence_id,source_id,source_item_id,source_uri,document_id,element_id,agentic_memory_id,ingestion_run_id,content_hash,metadata)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (
                str(e.evidence_id),
                str(e.source_id),
                str(e.source_item_id),
                e.source_uri,
                e.document_id,
                e.element_id,
                e.agentic_memory_id,
                str(e.ingestion_run_id),
                e.content_hash,
                json_param(e.metadata),
            ),
        )
