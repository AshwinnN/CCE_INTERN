-- Physical metadata: tables, columns, constraints -- all snapshot-scoped.
--
-- table_id / column_id / constraint_id are deterministic (uuid5, derived
-- from a stable natural key -- schema_id+table_name, table_id+column_name,
-- etc; see repository/postgresql_metadata_repository.py's _stable_uuid()),
-- NOT a fresh random UUID per snapshot. That makes the *same* id identify
-- the *same* table/column across every snapshot it appears in, so
-- tools/schema_change_detector.py can diff two snapshots by id instead of
-- by name, and a retried ingestion run for the same snapshot_id upserts
-- via ON CONFLICT (id, snapshot_id) DO UPDATE SET updated_at = now()
-- without ever touching another snapshot's rows -- immutability preserved,
-- retries still safe.
--
-- data_type is the CCE canonical type (connectors/canonical_types.py);
-- native_data_type + type_detail preserve source fidelity -- see
-- canonical_types_implementation_diagram.md "Issue 5: Canonical Types".
CREATE TABLE IF NOT EXISTS cce_table (
    table_id      UUID NOT NULL,
    snapshot_id   UUID NOT NULL REFERENCES cce_schema_snapshot(snapshot_id),
    schema_id     UUID NOT NULL REFERENCES cce_schema(schema_id),
    table_name    TEXT NOT NULL,
    table_type    TEXT NOT NULL DEFAULT 'TABLE',   -- 'TABLE', 'VIEW', ...
    description   TEXT,
    row_count     BIGINT,
    is_temporary  BOOLEAN NOT NULL DEFAULT false,
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (table_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_cce_table_snapshot ON cce_table(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_cce_table_schema_name ON cce_table(schema_id, table_name);

CREATE TABLE IF NOT EXISTS cce_column (
    column_id                UUID NOT NULL,
    snapshot_id               UUID NOT NULL REFERENCES cce_schema_snapshot(snapshot_id),
    table_id                  UUID NOT NULL,
    column_name               TEXT NOT NULL,
    ordinal_position           INT NOT NULL,
    data_type                 TEXT NOT NULL,      -- canonical (connectors/canonical_types.py)
    type_detail                JSONB NOT NULL DEFAULT '{}'::jsonb,
    native_data_type           TEXT NOT NULL,      -- original vendor type string
    is_nullable                BOOLEAN NOT NULL DEFAULT true,
    numeric_precision          INT,
    numeric_scale              INT,
    character_maximum_length   INT,
    description                TEXT,
    metadata                   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (column_id, snapshot_id),
    FOREIGN KEY (table_id, snapshot_id) REFERENCES cce_table(table_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_cce_column_snapshot ON cce_column(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_cce_column_data_type ON cce_column(data_type);
CREATE INDEX IF NOT EXISTS idx_cce_column_native_type ON cce_column(native_data_type);
CREATE INDEX IF NOT EXISTS idx_cce_column_table_ordinal ON cce_column(table_id, ordinal_position);

CREATE TABLE IF NOT EXISTS cce_constraint (
    constraint_id   UUID NOT NULL,
    snapshot_id     UUID NOT NULL REFERENCES cce_schema_snapshot(snapshot_id),
    table_id        UUID NOT NULL,
    constraint_name TEXT NOT NULL,
    constraint_type TEXT NOT NULL CHECK (
        constraint_type IN ('PRIMARY_KEY', 'UNIQUE', 'FOREIGN_KEY', 'NOT_NULL', 'CHECK')),
    -- Ordered column names this constraint covers. A JSONB array here
    -- (rather than a junction table) is sufficient because a same-table
    -- constraint's own column list is never queried by target column the
    -- way a cross-table relationship is -- Issue 2's junction table
    -- (04_relationships.sql) is reserved for that case.
    column_names    JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (constraint_id, snapshot_id),
    FOREIGN KEY (table_id, snapshot_id) REFERENCES cce_table(table_id, snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_cce_constraint_snapshot ON cce_constraint(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_cce_constraint_table ON cce_constraint(table_id);
