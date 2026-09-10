-- Fail rather than guess client ownership of existing development records.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM cce_source s LEFT JOIN source_domain d USING(source_id)
           GROUP BY s.source_id HAVING count(d.domain_id) <> 1) THEN
   RAISE EXCEPTION 'Workspace migration requires exactly one existing domain association per source; resolve unassigned or multi-domain sources before migration';
 END IF;
 IF EXISTS(SELECT lower(name) FROM domain GROUP BY lower(name) HAVING count(*)>1) THEN
   RAISE EXCEPTION 'Workspace migration: case-insensitive duplicate names must be resolved';
 END IF;
END $$;
ALTER TABLE domain RENAME TO workspace;
ALTER TABLE workspace RENAME COLUMN domain_id TO workspace_uuid;
ALTER TABLE workspace ADD COLUMN workspace_id text;
ALTER TABLE workspace ADD COLUMN created_by text NOT NULL DEFAULT 'migration';
ALTER TABLE workspace ADD COLUMN status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','ARCHIVED'));
UPDATE workspace SET workspace_id=name||'_workspace',status=CASE WHEN enabled THEN 'ACTIVE' ELSE 'ARCHIVED' END;
ALTER TABLE workspace ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE workspace ADD UNIQUE(workspace_id);
CREATE UNIQUE INDEX workspace_name_ci ON workspace(lower(name));
ALTER TABLE workspace DROP COLUMN tags, DROP COLUMN metadata, DROP COLUMN enabled;
ALTER TABLE cce_source ADD COLUMN workspace_uuid uuid REFERENCES workspace(workspace_uuid);
UPDATE cce_source s SET workspace_uuid=d.domain_id FROM source_domain d WHERE d.source_id=s.source_id;
ALTER TABLE cce_source ALTER COLUMN workspace_uuid SET NOT NULL;
ALTER TABLE cce_source RENAME COLUMN account_id TO name;
ALTER TABLE cce_source RENAME COLUMN adapter TO source_type;
ALTER TABLE cce_source ADD COLUMN archived_at timestamptz;
DO $$ DECLARE c record; BEGIN
 FOR c IN SELECT conname FROM pg_constraint WHERE conrelid='cce_source'::regclass AND contype='u' LOOP
  EXECUTE format('ALTER TABLE cce_source DROP CONSTRAINT %I',c.conname);
 END LOOP;
END $$;
UPDATE cce_source SET source_type='azure_blob' WHERE source_type='azure-blob';
CREATE UNIQUE INDEX source_workspace_name_ci ON cce_source(workspace_uuid,lower(name));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['candidate_extraction','proposal_batch','context_asset','context_package','graph_entity','graph_edge','query_trace'] LOOP
  EXECUTE format('ALTER TABLE %I RENAME COLUMN domain_id TO workspace_uuid',t);
 END LOOP;
END $$;
-- Existing associations must agree with their evidence ownership.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM candidate_extraction c JOIN source_item i USING(source_item_id) JOIN cce_source s USING(source_id) WHERE c.workspace_uuid<>s.workspace_uuid)
 OR EXISTS(SELECT 1 FROM proposal_batch b JOIN cce_ingestion_run r ON r.run_id=b.ingestion_run_id JOIN cce_source s USING(source_id) WHERE b.workspace_uuid<>s.workspace_uuid) THEN
  RAISE EXCEPTION 'Workspace migration: historical evidence ownership is ambiguous';
 END IF;
END $$;
UPDATE candidate_extraction SET payload=(payload-'domain_id')||jsonb_build_object('workspace_uuid',workspace_uuid);
INSERT INTO context_package(package_id,workspace_uuid,name)
 SELECT gen_random_uuid(),w.workspace_uuid,w.name||'_package' FROM workspace w
 WHERE NOT EXISTS(SELECT 1 FROM context_package p WHERE p.workspace_uuid=w.workspace_uuid);
DROP TABLE source_domain_detection;
DROP TABLE source_domain;
ALTER TABLE ingestion_item_result DROP CONSTRAINT ingestion_item_result_processing_status_check;
UPDATE ingestion_item_result SET processing_status='FAILED' WHERE processing_status='DOMAIN_UNRESOLVED';
ALTER TABLE ingestion_item_result ADD CHECK(processing_status IN ('PENDING','PROCESSING','SUCCESS','FAILED'));
ALTER TABLE ingestion_item_result DROP COLUMN detected_domains;
ALTER TABLE cce_ingestion_run DROP CONSTRAINT cce_ingestion_run_status_check;
UPDATE cce_ingestion_run SET status='SUCCESS' WHERE status='COMPLETE';
ALTER TABLE cce_ingestion_run ADD CHECK(status IN ('RUNNING','SUCCESS','PARTIAL','FAILED'));
ALTER TABLE proposal_batch ADD UNIQUE(ingestion_run_id);
ALTER TABLE query_trace ADD COLUMN response jsonb;
ALTER TABLE query_trace ADD COLUMN parent_trace_id uuid REFERENCES query_trace(trace_id);
ALTER TABLE query_trace DROP COLUMN context_on, DROP COLUMN context_off;
CREATE OR REPLACE FUNCTION cce_workspace_identifier_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.workspace_id<>OLD.workspace_id THEN RAISE EXCEPTION 'Workspace identifier is immutable'; END IF; RETURN NEW; END $$;
CREATE TRIGGER workspace_identifier_immutable BEFORE UPDATE ON workspace FOR EACH ROW EXECUTE FUNCTION cce_workspace_identifier_immutable();
-- Feedback embeddings are never stored as a raw Postgres vector column: they go
-- through the same AgenticPlane/local-index boundary as every other embedding
-- (see cce.runtime.feedback.FeedbackService and ADR-003), so this table never
-- requires the Postgres `vector` extension -- notably including on Azure
-- Database for PostgreSQL, where `vector` is not allow-listed by default.
CREATE TABLE query_feedback(
 feedback_id uuid PRIMARY KEY,trace_id uuid NOT NULL REFERENCES query_trace,
 workspace_uuid uuid NOT NULL REFERENCES workspace, rating text NOT NULL CHECK(rating IN ('GOOD','BAD')),
 user_comment text NOT NULL DEFAULT '',question text NOT NULL,answer text NOT NULL,
 package_version_id uuid REFERENCES package_version,context_used jsonb NOT NULL,citations jsonb NOT NULL,
 issue_category text,generated_critique text,inference_confidence double precision CHECK(inference_confidence BETWEEN 0 AND 1),
 lesson_eligible boolean NOT NULL,created_by text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(trace_id,created_by));
CREATE INDEX feedback_workspace ON query_feedback(workspace_uuid) WHERE lesson_eligible;
