from uuid import uuid4

from cce.ingestion.lifecycle_models import SourceRunRequest


class JobRepository:
    def __init__(self, db, lease_seconds):
        self.db = db
        self.lease_seconds = lease_seconds

    def claim(self) -> SourceRunRequest | None:
        with self.db.transaction() as cur:
            cur.execute("""SELECT * FROM cce_job WHERE status='QUEUED' OR (status='RUNNING' AND lease_until<now())
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""")
            row = cur.fetchone()
            if not row:
                return None
            token = uuid4()
            cur.execute(
                "UPDATE cce_job SET status='RUNNING',claim_token=%s,attempt_count=attempt_count+1,claimed_at=now(),lease_until=now()+(%s * interval '1 second') WHERE job_id=%s",
                (str(token), self.lease_seconds, str(row["job_id"])),
            )
            return SourceRunRequest(
                ingestion_run_id=row["ingestion_run_id"],
                source_id=row["source_id"],
                claim_token=token,
            )

    def renew(self, request) -> bool:
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE cce_job SET lease_until=now()+(%s * interval '1 second'),updated_at=now() WHERE ingestion_run_id=%s AND claim_token=%s AND status='RUNNING' AND lease_until>now()",
                (
                    self.lease_seconds,
                    str(request.ingestion_run_id),
                    str(request.claim_token),
                ),
            )
            return cur.rowcount == 1

    def finish(self, request, error=None):
        with self.db.transaction() as cur:
            cur.execute(
                "UPDATE cce_job SET status=%s,error=%s,lease_until=NULL,updated_at=now() WHERE ingestion_run_id=%s AND claim_token=%s AND status='RUNNING' AND lease_until>now()",
                (
                    "FAILED" if error else "COMPLETE",
                    error,
                    str(request.ingestion_run_id),
                    str(request.claim_token),
                ),
            )
            if error and cur.rowcount:
                cur.execute(
                    "UPDATE cce_ingestion_run SET status='FAILED',error_message=%s,finished_at=now() WHERE run_id=%s AND status='RUNNING'",
                    (error, str(request.ingestion_run_id)),
                )
