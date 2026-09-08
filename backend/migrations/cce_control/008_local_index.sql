-- CREATE EXTENSION IF NOT EXISTS vector;

-- CREATE TABLE IF NOT EXISTS cce_local_index_chunk (
--     chunk_id UUID PRIMARY KEY,
--     document_id TEXT NOT NULL,
--     source_id UUID NOT NULL REFERENCES cce_source(source_id),
--     chunk_text TEXT NOT NULL,
--     embedding vector(768) NOT NULL,
--     source_ref TEXT NOT NULL,
--     version TEXT,
--     object_id TEXT NOT NULL,
--     trace_id TEXT,
--     metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
--     created_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );

-- CREATE INDEX IF NOT EXISTS idx_cce_local_index_source
--     ON cce_local_index_chunk(source_id);

-- CREATE INDEX IF NOT EXISTS idx_cce_local_index_embedding
--     ON cce_local_index_chunk
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);
