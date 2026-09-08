ALTER TABLE cce_ingestion_run DROP CONSTRAINT IF EXISTS cce_ingestion_run_status_check;
UPDATE cce_ingestion_run SET status='COMPLETE' WHERE status='SUCCESS';
ALTER TABLE cce_ingestion_run ADD CONSTRAINT cce_ingestion_run_status_check CHECK(status IN ('RUNNING','PARTIAL','COMPLETE','FAILED'));
-- Existing duplicate unfinished legacy runs must be resolved by an operator before upgrading.
CREATE UNIQUE INDEX IF NOT EXISTS one_resumable_source_run ON cce_ingestion_run(source_id) WHERE status IN ('RUNNING','PARTIAL');
CREATE TABLE IF NOT EXISTS ingestion_item_result (
 ingestion_run_id uuid REFERENCES cce_ingestion_run(run_id), source_item_id uuid REFERENCES source_item,
 change_type text NOT NULL CHECK(change_type IN ('NEW','CHANGED','UNCHANGED','MISSING')),
 processing_status text NOT NULL CHECK(processing_status IN ('PENDING','PROCESSING','SUCCESS','FAILED','DOMAIN_UNRESOLVED')),
 content_hash text, detected_domains jsonb NOT NULL DEFAULT '[]', error text,
 metadata jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(ingestion_run_id,source_item_id));
CREATE TABLE IF NOT EXISTS cce_job (
 job_id uuid PRIMARY KEY, job_type text NOT NULL DEFAULT 'INGEST_SOURCE', ingestion_run_id uuid NOT NULL UNIQUE REFERENCES cce_ingestion_run(run_id),
 source_id uuid NOT NULL REFERENCES cce_source, status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','COMPLETE','FAILED')),
 attempt_count int NOT NULL DEFAULT 0, lease_until timestamptz, claimed_at timestamptz, claim_token uuid,
 error text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS query_trace (
 trace_id uuid PRIMARY KEY, question text NOT NULL, actor_id text, domain_id uuid REFERENCES domain,
 package_version_id uuid REFERENCES package_version, status text NOT NULL, context_on jsonb, context_off jsonb,
 proof jsonb, errors jsonb NOT NULL DEFAULT '[]', created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz, metadata jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS query_node_trace (
 node_trace_id uuid PRIMARY KEY, trace_id uuid NOT NULL REFERENCES query_trace, node_name text NOT NULL,
 started_at timestamptz NOT NULL, finished_at timestamptz NOT NULL, duration double precision NOT NULL,
 model_name text, structured_input jsonb, structured_output jsonb, error jsonb);
CREATE TABLE IF NOT EXISTS sql_attempt (
 attempt_id uuid PRIMARY KEY, trace_id uuid NOT NULL REFERENCES query_trace, branch text NOT NULL CHECK(branch IN ('ON','OFF')),
 attempt_no int NOT NULL, sql text, parse_result jsonb, validation_result jsonb, guard_result jsonb,
 database_error text, correction_guidance text, status text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(trace_id,branch,attempt_no));
