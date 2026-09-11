from uuid import uuid4

from cce.context_packages.models.assets import Evidence
from cce.governance.models import Candidate
from cce.ingestion.lifecycle_models import (
    IngestionRun,
    InventoryResult,
    ItemResult,
    SourceItem,
    SourceRunRequest,
)
from cce.persistence.postgres.lifecycle_db import json_param


class IngestionRepository:
    def __init__(self, db):
        self.db = db

    def create_or_resume(self, source_id) -> IngestionRun:
        with self.db.transaction() as cur:
            cur.execute(
                "SELECT source_id FROM cce_source WHERE source_id=%s FOR UPDATE",
                (str(source_id),),
            )
            if not cur.fetchone():
                raise KeyError("Source not found")
            cur.execute(
                "SELECT r.run_id,r.status FROM cce_ingestion_run r WHERE r.source_id=%s AND (r.status IN ('RUNNING','PARTIAL') OR (r.status='COMPLETE' AND EXISTS(SELECT 1 FROM cce_job j WHERE j.ingestion_run_id=r.run_id AND j.status='FAILED'))) ORDER BY r.started_at LIMIT 1",
                (str(source_id),),
            )
            row = cur.fetchone()
            rid = row["run_id"] if row else uuid4()
            if not row:
                cur.execute(
                    "INSERT INTO cce_ingestion_run(run_id,source_id,status,trace_id) VALUES(%s,%s,'RUNNING',%s)",
                    (str(rid), str(source_id), str(rid)),
                )
            # Never disturb a live lease. Explicit retry requeues PARTIAL/failed jobs.
            cur.execute(
                """INSERT INTO cce_job(job_id,ingestion_run_id,source_id,status) VALUES(%s,%s,%s,'QUEUED')
                ON CONFLICT(ingestion_run_id) DO UPDATE SET status=CASE WHEN cce_job.status='RUNNING' AND cce_job.lease_until>now()
                THEN 'RUNNING' ELSE 'QUEUED' END,updated_at=now()""",
                (str(uuid4()), str(rid), str(source_id)),
            )
        return self.get(rid)

    def get(self, run_id) -> IngestionRun:
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT run_id::text ingestion_run_id,source_id::text,status,objects_processed,objects_failed,error_message error
                FROM cce_ingestion_run WHERE run_id=%s""",
                (str(run_id),),
            )
            row = cur.fetchone()
            if not row:
                raise KeyError("Ingestion run not found")
            return IngestionRun.model_validate(dict(row))

    def assert_lease(self, cur, request):
        cur.execute(
            "SELECT job_id FROM cce_job WHERE ingestion_run_id=%s AND claim_token=%s AND status='RUNNING' AND lease_until>now() FOR SHARE",
            (str(request.ingestion_run_id), str(request.claim_token)),
        )
        if not cur.fetchone():
            raise RuntimeError("Ingestion lease lost")

    def inventory(
        self, request: SourceRunRequest, items: list[SourceItem]
    ) -> InventoryResult:
        with self.db.transaction() as cur:
            self.assert_lease(cur, request)
            cur.execute(
                "SELECT * FROM source_item WHERE source_id=%s",
                (str(request.source_id),),
            )
            old = [dict(r) for r in cur.fetchall()]
            seen = set()
            result = []
            for item in items:
                prior = next(
                    (
                        r
                        for r in old
                        if (
                            item.source_native_id
                            and r["source_native_id"] == item.source_native_id
                        )
                        or (
                            not item.source_native_id
                            and r["canonical_uri"] == item.canonical_uri
                        )
                    ),
                    None,
                )
                if prior:
                    item.source_item_id = prior["source_item_id"]
                    item.change_type = (
                        "UNCHANGED"
                        if prior["current_content_hash"] == item.content_hash
                        and prior["availability_status"] == "AVAILABLE"
                        else "CHANGED"
                    )
                else:
                    item.change_type = "NEW"
                seen.add(str(item.source_item_id))
                cur.execute(
                    """INSERT INTO source_item(source_item_id,source_id,source_native_id,canonical_uri,first_seen_run_id,last_seen_run_id,metadata)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(source_item_id) DO UPDATE SET last_seen_run_id=excluded.last_seen_run_id,
                    canonical_uri=excluded.canonical_uri,metadata=excluded.metadata,updated_at=now()""",
                    (
                        str(item.source_item_id),
                        str(item.source_id),
                        item.source_native_id,
                        item.canonical_uri,
                        str(request.ingestion_run_id),
                        str(request.ingestion_run_id),
                        json_param(item.metadata),
                    ),
                )
                cur.execute(
                    "SELECT processing_status,content_hash FROM ingestion_item_result WHERE ingestion_run_id=%s AND source_item_id=%s",
                    (str(request.ingestion_run_id), str(item.source_item_id)),
                )
                previous = cur.fetchone()
                if previous:
                    item.change_type = (
                        "UNCHANGED"
                        if previous["processing_status"] == "SUCCESS"
                        and previous["content_hash"] == item.content_hash
                        else "CHANGED"
                    )
                result.append(item)
            for prior in old:
                if str(prior["source_item_id"]) not in seen:
                    result.append(
                        SourceItem(
                            source_item_id=prior["source_item_id"],
                            source_id=request.source_id,
                            source_native_id=prior["source_native_id"],
                            canonical_uri=prior["canonical_uri"],
                            content_hash=prior["current_content_hash"] or "",
                            change_type="MISSING",
                            metadata=prior["metadata"],
                        )
                    )
            # Record all missing availability before alternate-evidence checks (including two deletions in one run).
            missing = [
                str(i.source_item_id) for i in result if i.change_type == "MISSING"
            ]
            if missing:
                cur.execute(
                    "UPDATE source_item SET availability_status='MISSING',updated_at=now() WHERE source_item_id::text=ANY(%s)",
                    (missing,),
                )
            cur.execute(
                "UPDATE cce_ingestion_run SET status='RUNNING' WHERE run_id=%s",
                (str(request.ingestion_run_id),),
            )
        return InventoryResult(items=result)

    def save_result(
        self, request: SourceRunRequest, result: ItemResult, candidates: list[Candidate]
    ):
        i = result.item
        with self.db.transaction() as cur:
            self.assert_lease(cur, request)
            cur.execute(
                """INSERT INTO ingestion_item_result(ingestion_run_id,source_item_id,change_type,processing_status,content_hash,detected_domains,error)
                VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(ingestion_run_id,source_item_id) DO UPDATE SET
                change_type=excluded.change_type,processing_status=excluded.processing_status,content_hash=excluded.content_hash,
                detected_domains=excluded.detected_domains,error=excluded.error,updated_at=now()""",
                (
                    str(request.ingestion_run_id),
                    str(i.source_item_id),
                    i.change_type,
                    result.status,
                    i.content_hash,
                    json_param([d.model_dump(mode="json") for d in result.domains]),
                    result.error,
                ),
            )
            if i.change_type != "UNCHANGED":
                cur.execute(
                    "DELETE FROM candidate_extraction WHERE ingestion_run_id=%s AND source_item_id=%s",
                    (str(request.ingestion_run_id), str(i.source_item_id)),
                )
                for c in candidates:
                    cur.execute(
                        "INSERT INTO candidate_extraction(candidate_id,ingestion_run_id,source_item_id,domain_id,asset_type,canonical_key,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (
                            str(uuid4()),
                            str(request.ingestion_run_id),
                            str(i.source_item_id),
                            str(c.domain_id),
                            c.payload.asset_type,
                            c.payload.canonical_key,
                            json_param(c),
                        ),
                    )
            if result.status == "SUCCESS":
                cur.execute(
                    "UPDATE source_item SET current_content_hash=%s,availability_status=%s,updated_at=now() WHERE source_item_id=%s",
                    (
                        i.content_hash,
                        "MISSING" if i.change_type == "MISSING" else "AVAILABLE",
                        str(i.source_item_id),
                    ),
                )

    def detections(self, request, item, candidates, selected):
        with self.db.transaction() as cur:
            self.assert_lease(cur, request)
            for d in candidates:
                cur.execute(
                    """INSERT INTO source_domain_detection(detection_id,ingestion_run_id,source_id,source_item_id,domain_id,confidence,rationale,selected)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        str(uuid4()),
                        str(request.ingestion_run_id),
                        str(item.source_id),
                        str(item.source_item_id),
                        str(d.domain_id),
                        d.confidence,
                        d.rationale,
                        d.domain_id in selected,
                    ),
                )

    def finish(self, request, results: list[ItemResult]) -> IngestionRun:
        failures = [r for r in results if r.status != "SUCCESS"]
        with self.db.transaction() as cur:
            self.assert_lease(cur, request)
            cur.execute(
                "UPDATE cce_ingestion_run SET status=%s,objects_processed=%s,objects_failed=%s,error_message=%s,finished_at=now() WHERE run_id=%s",
                (
                    "PARTIAL" if failures else "COMPLETE",
                    len(results) - len(failures),
                    len(failures),
                    "; ".join(r.error or str(r.status) for r in failures) or None,
                    str(request.ingestion_run_id),
                ),
            )
            if not failures:
                cur.execute(
                    "DELETE FROM source_domain WHERE source_id=%s",
                    (str(request.source_id),),
                )
                # Latest detection per available item/domain, retaining unchanged successful history.
                cur.execute(
                    """INSERT INTO source_domain(source_id,domain_id,confidence,ingestion_run_id,rationale)
                    SELECT %s,domain_id,max(confidence),%s,string_agg(DISTINCT rationale,'; ') FROM (
                    SELECT DISTINCT ON(d.source_item_id,d.domain_id) d.domain_id,d.confidence,d.rationale,d.selected
                    FROM source_domain_detection d JOIN source_item i USING(source_item_id)
                    WHERE d.source_id=%s AND i.availability_status='AVAILABLE' AND d.created_at=(SELECT max(d2.created_at) FROM source_domain_detection d2 WHERE d2.source_item_id=d.source_item_id)
                    ORDER BY d.source_item_id,d.domain_id,d.created_at DESC) latest WHERE selected GROUP BY domain_id""",
                    (
                        str(request.source_id),
                        str(request.ingestion_run_id),
                        str(request.source_id),
                    ),
                )
        return self.get(request.ingestion_run_id)

    def promotion_domains(self, run_id):
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT domain_id::text FROM candidate_extraction WHERE ingestion_run_id=%s
                UNION SELECT domain_id::text FROM source_domain WHERE ingestion_run_id=%s""",
                (str(run_id), str(run_id)),
            )
            return [r["domain_id"] for r in cur.fetchall()]

    def missing_candidates(self, item) -> list[Candidate]:
        with self.db.transaction() as cur:
            cur.execute(
                """SELECT DISTINCT a.asset_id,a.domain_id,r.payload FROM context_asset a
                JOIN context_asset_revision r USING(asset_id) JOIN package_asset pa USING(asset_revision_id)
                JOIN package_version v USING(package_version_id) JOIN asset_revision_evidence ae USING(asset_revision_id)
                JOIN context_evidence e USING(evidence_id) WHERE v.status='ACTIVE' AND e.source_item_id=%s
                AND NOT EXISTS(SELECT 1 FROM asset_revision_evidence ae2 JOIN context_evidence e2 USING(evidence_id)
                JOIN source_item i2 USING(source_item_id) WHERE ae2.asset_revision_id=r.asset_revision_id AND i2.availability_status='AVAILABLE')""",
                (str(item.source_item_id),),
            )
            rows = cur.fetchall()
            out = []
            for row in rows:
                cur.execute(
                    "SELECT * FROM context_evidence WHERE source_item_id=%s",
                    (str(item.source_item_id),),
                )
                evidence = [Evidence.model_validate(dict(r)) for r in cur.fetchall()]
                out.append(
                    Candidate(
                        domain_id=row["domain_id"],
                        payload=row["payload"],
                        evidence=evidence,
                        operation="REMOVE",
                        target_asset_id=row["asset_id"],
                    )
                )
            return out
