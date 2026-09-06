ALTER TABLE cce_source
    ADD COLUMN IF NOT EXISTS kind TEXT CHECK (kind IN ('structured', 'unstructured')),
    ADD COLUMN IF NOT EXISTS credential_ref TEXT,
    ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_cce_source_enabled ON cce_source(enabled);

CREATE TABLE IF NOT EXISTS cce_ingestion_run (
    run_id UUID PRIMARY KEY,
    source_id UUID NOT NULL REFERENCES cce_source(source_id),
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    objects_processed INT NOT NULL DEFAULT 0,
    objects_failed INT NOT NULL DEFAULT 0,
    error_message TEXT,
    trace_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_cce_ingestion_run_source_started
    ON cce_ingestion_run(source_id, started_at DESC);
