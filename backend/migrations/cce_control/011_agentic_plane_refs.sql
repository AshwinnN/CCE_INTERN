CREATE TABLE IF NOT EXISTS cce_agentic_plane_memory (
    document_id TEXT NOT NULL,
    chunk_index INT NOT NULL,
    memory_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    source_id UUID,
    trace_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_apm_memory_id
    ON cce_agentic_plane_memory(memory_id);
