-- Every ingestion run for a schema creates one immutable snapshot. Every
-- row in 03_metadata.sql / 04_relationships.sql is scoped to a snapshot_id
-- and is never updated except its own `updated_at` (idempotent retry of the
-- same snapshot only) -- see MASTER_INDEX.md "Issue 4: Snapshot Linking"
-- and "Issue 3: Relationship Versioning". Old snapshots are never mutated,
-- which is what makes schema history queryable and change detection
-- (tools/schema_change_detector.py) a diff between two snapshot_ids.
CREATE TABLE IF NOT EXISTS cce_schema_snapshot (
    snapshot_id   UUID PRIMARY KEY,
    source_id     UUID NOT NULL REFERENCES cce_source(source_id),
    schema_id     UUID REFERENCES cce_schema(schema_id),
    captured_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    schema_hash   TEXT NOT NULL,          -- hash of every table/column name+type in this snapshot
    status        TEXT NOT NULL CHECK (status IN ('SUCCESS', 'PARTIAL', 'FAILED')),
    table_count   INT,
    column_count  INT,
    error_detail  TEXT
);

CREATE INDEX IF NOT EXISTS idx_cce_snapshot_source_captured
    ON cce_schema_snapshot(source_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_cce_snapshot_schema_captured
    ON cce_schema_snapshot(schema_id, captured_at DESC);
