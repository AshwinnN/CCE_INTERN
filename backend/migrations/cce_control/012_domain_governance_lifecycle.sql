CREATE TABLE IF NOT EXISTS domain (
 domain_id uuid PRIMARY KEY, name text NOT NULL UNIQUE, description text NOT NULL DEFAULT '',
 tags jsonb NOT NULL DEFAULT '[]', metadata jsonb NOT NULL DEFAULT '{}', enabled boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS source_item (
 source_item_id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES cce_source,
 source_native_id text, canonical_uri text NOT NULL, current_content_hash text,
 availability_status text NOT NULL DEFAULT 'AVAILABLE', first_seen_run_id uuid REFERENCES cce_ingestion_run(run_id),
 last_seen_run_id uuid REFERENCES cce_ingestion_run(run_id), metadata jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS source_item_native ON source_item(source_id,source_native_id) WHERE source_native_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS source_item_uri ON source_item(source_id,canonical_uri) WHERE source_native_id IS NULL;
CREATE TABLE IF NOT EXISTS source_domain_detection (
 detection_id uuid PRIMARY KEY, ingestion_run_id uuid NOT NULL REFERENCES cce_ingestion_run(run_id),
 source_id uuid NOT NULL REFERENCES cce_source, source_item_id uuid NOT NULL REFERENCES source_item,
 domain_id uuid NOT NULL REFERENCES domain, confidence double precision NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 rationale text NOT NULL, selected boolean NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS source_domain (
 source_id uuid REFERENCES cce_source, domain_id uuid REFERENCES domain, confidence double precision NOT NULL,
 ingestion_run_id uuid NOT NULL REFERENCES cce_ingestion_run(run_id), rationale text NOT NULL,
 detected_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}', PRIMARY KEY(source_id,domain_id));
CREATE TABLE IF NOT EXISTS candidate_extraction (
 candidate_id uuid PRIMARY KEY, ingestion_run_id uuid NOT NULL REFERENCES cce_ingestion_run(run_id),
 source_item_id uuid NOT NULL REFERENCES source_item, domain_id uuid NOT NULL REFERENCES domain,
 asset_type text NOT NULL, canonical_key text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS proposal_batch (
 proposal_batch_id uuid PRIMARY KEY, ingestion_run_id uuid NOT NULL REFERENCES cce_ingestion_run(run_id),
 domain_id uuid NOT NULL REFERENCES domain, status text NOT NULL CHECK(status IN ('READY_FOR_REVIEW','NO_CHANGE','BUILD_BLOCKED','PACKAGED')),
 proposal_count int NOT NULL DEFAULT 0, validation_errors jsonb NOT NULL DEFAULT '[]',
 created_at timestamptz NOT NULL DEFAULT now(), packaged_at timestamptz, UNIQUE(ingestion_run_id,domain_id));
CREATE TABLE IF NOT EXISTS context_asset (
 asset_id uuid PRIMARY KEY, domain_id uuid NOT NULL REFERENCES domain, asset_type text NOT NULL,
 canonical_key text NOT NULL, is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
 retired_at timestamptz, metadata jsonb NOT NULL DEFAULT '{}', UNIQUE(domain_id,asset_type,canonical_key));
CREATE TABLE IF NOT EXISTS proposal (
 proposal_id uuid PRIMARY KEY, proposal_batch_id uuid NOT NULL REFERENCES proposal_batch,
 operation text NOT NULL CHECK(operation IN ('CREATE','UPDATE','REMOVE')), target_asset_id uuid REFERENCES context_asset,
 asset_type text NOT NULL, canonical_key text NOT NULL, machine_payload jsonb NOT NULL, reviewed_payload jsonb NOT NULL,
 status text NOT NULL DEFAULT 'PROPOSED' CHECK(status IN ('PROPOSED','APPROVED','REJECTED')),
 resolved_at timestamptz, resolved_by text, created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}',
 CHECK(operation='CREATE' OR target_asset_id IS NOT NULL));
CREATE TABLE IF NOT EXISTS proposal_review_action (
 action_id uuid PRIMARY KEY, proposal_id uuid NOT NULL REFERENCES proposal, actor_id text NOT NULL,
 action text NOT NULL CHECK(action IN ('EDIT','APPROVE','REJECT')), previous_payload jsonb, new_payload jsonb,
 comment text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS context_asset_revision (
 asset_revision_id uuid PRIMARY KEY, asset_id uuid NOT NULL REFERENCES context_asset, revision_no int NOT NULL,
 payload jsonb NOT NULL, metadata jsonb NOT NULL DEFAULT '{}', created_from_proposal_id uuid NOT NULL REFERENCES proposal,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(asset_id,revision_no));
CREATE TABLE IF NOT EXISTS context_evidence (
 evidence_id uuid PRIMARY KEY, source_id uuid NOT NULL REFERENCES cce_source, source_item_id uuid NOT NULL REFERENCES source_item,
 source_uri text NOT NULL, document_id text NOT NULL, element_id text, agentic_memory_id text,
 ingestion_run_id uuid NOT NULL REFERENCES cce_ingestion_run(run_id), content_hash text NOT NULL, metadata jsonb NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS evidence_memory_idx ON context_evidence(agentic_memory_id);
CREATE TABLE IF NOT EXISTS proposal_evidence (
 proposal_id uuid REFERENCES proposal, evidence_id uuid REFERENCES context_evidence, PRIMARY KEY(proposal_id,evidence_id));
CREATE TABLE IF NOT EXISTS asset_revision_evidence (
 asset_revision_id uuid REFERENCES context_asset_revision, evidence_id uuid REFERENCES context_evidence, PRIMARY KEY(asset_revision_id,evidence_id));
CREATE TABLE IF NOT EXISTS context_package (
 package_id uuid PRIMARY KEY, domain_id uuid NOT NULL UNIQUE REFERENCES domain, name text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS package_version (
 package_version_id uuid PRIMARY KEY, package_id uuid NOT NULL REFERENCES context_package, version_no int NOT NULL,
 status text NOT NULL CHECK(status IN ('ACTIVE','SUPERSEDED')), created_from_proposal_batch_id uuid NOT NULL UNIQUE REFERENCES proposal_batch,
 created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}', UNIQUE(package_id,version_no));
CREATE UNIQUE INDEX IF NOT EXISTS one_active_package_version ON package_version(package_id) WHERE status='ACTIVE';
CREATE TABLE IF NOT EXISTS package_asset (
 package_version_id uuid REFERENCES package_version, asset_revision_id uuid REFERENCES context_asset_revision,
 PRIMARY KEY(package_version_id,asset_revision_id));
CREATE TABLE IF NOT EXISTS package_snapshot (
 package_version_id uuid PRIMARY KEY REFERENCES package_version, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS graph_entity (
 entity_id uuid PRIMARY KEY, domain_id uuid NOT NULL REFERENCES domain, canonical_key text NOT NULL, entity_type text NOT NULL,
 asset_revision_id uuid NOT NULL UNIQUE REFERENCES context_asset_revision, metadata jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS graph_edge (
 edge_id uuid PRIMARY KEY, domain_id uuid NOT NULL REFERENCES domain, from_entity_id uuid NOT NULL REFERENCES graph_entity,
 to_entity_id uuid NOT NULL REFERENCES graph_entity, relation_type text NOT NULL,
 asset_revision_id uuid NOT NULL REFERENCES context_asset_revision, metadata jsonb NOT NULL DEFAULT '{}',
 UNIQUE(asset_revision_id,from_entity_id,to_entity_id));
-- Immutable historical artifacts, including machine proposals and append-only review history.
CREATE OR REPLACE FUNCTION cce_forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'CCE historical records are immutable'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['context_asset_revision','context_evidence','proposal_review_action','source_domain_detection','package_snapshot','package_asset'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname=t||'_immutable') THEN
 EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION cce_forbid_mutation()',t||'_immutable',t);
 END IF;
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION cce_proposal_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.machine_payload IS DISTINCT FROM NEW.machine_payload OR OLD.status <> 'PROPOSED' THEN
 RAISE EXCEPTION 'Machine proposal and resolved proposals are immutable'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='proposal_immutable') THEN
 CREATE TRIGGER proposal_immutable BEFORE UPDATE ON proposal FOR EACH ROW EXECUTE FUNCTION cce_proposal_immutable();
 END IF;
END $$;
