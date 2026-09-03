-- CCE metadata repository: source -> namespace -> schema hierarchy.
-- Every structured source (Snowflake account, Postgres server, MySQL
-- server, ...) is one cce_source row; a catalog (Snowflake) or database
-- (Postgres/MySQL) under it is one cce_namespace row -- see
-- canonical_types_implementation_diagram.md / MASTER_INDEX.md "Issue 1:
-- Database vs Catalog": namespace_type carries the vendor-specific label
-- so a query can stay vendor-agnostic ("all namespaces for this source")
-- without ever branching on adapter name.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS cce_source (
    source_id     UUID PRIMARY KEY,
    adapter       TEXT NOT NULL,          -- 'snowflake', 'postgres', 'mysql', ...
    account_id    TEXT NOT NULL,          -- vendor account/project identifier
    display_name  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (adapter, account_id)
);

CREATE TABLE IF NOT EXISTS cce_namespace (
    namespace_id    UUID PRIMARY KEY,
    source_id       UUID NOT NULL REFERENCES cce_source(source_id),
    namespace_name  TEXT NOT NULL,
    namespace_type  TEXT NOT NULL CHECK (namespace_type IN ('catalog', 'database')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_id, namespace_name)
);

CREATE TABLE IF NOT EXISTS cce_schema (
    schema_id     UUID PRIMARY KEY,
    namespace_id  UUID NOT NULL REFERENCES cce_namespace(namespace_id),
    schema_name   TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (namespace_id, schema_name)
);

CREATE INDEX IF NOT EXISTS idx_cce_namespace_source ON cce_namespace(source_id);
CREATE INDEX IF NOT EXISTS idx_cce_schema_namespace ON cce_schema(namespace_id);
