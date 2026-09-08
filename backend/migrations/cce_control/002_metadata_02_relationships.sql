-- Table-to-table relationships (declared foreign keys and, later,
-- inferred ones). cce_relationship_column_mapping is the composite-key
-- junction table MASTER_INDEX.md's "Issue 2: Composite Keys" calls for --
-- a multi-column FK is one relationship row with N mapping rows (ordered
-- by ordinal_position), instead of cramming column pairs into JSONB.
CREATE TABLE IF NOT EXISTS cce_relationship (
    relationship_id   UUID NOT NULL,
    snapshot_id       UUID NOT NULL REFERENCES cce_schema_snapshot(snapshot_id),
    source_table_id   UUID NOT NULL,
    target_table_id   UUID NOT NULL,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('FOREIGN_KEY', 'INFERRED')),
    constraint_name   TEXT,
    confidence        NUMERIC(3, 2),   -- 1.00 for FOREIGN_KEY, < 1 for INFERRED (Phase 2+)
    description       TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (relationship_id, snapshot_id),
    FOREIGN KEY (source_table_id, snapshot_id) REFERENCES cce_table(table_id, snapshot_id),
    FOREIGN KEY (target_table_id, snapshot_id) REFERENCES cce_table(table_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_cce_relationship_snapshot ON cce_relationship(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_cce_relationship_source_table ON cce_relationship(source_table_id);
CREATE INDEX IF NOT EXISTS idx_cce_relationship_target_table ON cce_relationship(target_table_id);

CREATE TABLE IF NOT EXISTS cce_relationship_column_mapping (
    relationship_id   UUID NOT NULL,
    snapshot_id       UUID NOT NULL,
    ordinal_position  INT NOT NULL,
    source_column_id  UUID NOT NULL,
    target_column_id  UUID NOT NULL,
    PRIMARY KEY (relationship_id, snapshot_id, ordinal_position),
    FOREIGN KEY (relationship_id, snapshot_id) REFERENCES cce_relationship(relationship_id, snapshot_id),
    FOREIGN KEY (source_column_id, snapshot_id) REFERENCES cce_column(column_id, snapshot_id),
    FOREIGN KEY (target_column_id, snapshot_id) REFERENCES cce_column(column_id, snapshot_id)
);
