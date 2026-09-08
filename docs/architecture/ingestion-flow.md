# Ingestion Flow

Structured and unstructured ingestion are coordinated by
`cce.ingestion.orchestrator`; AgenticPlane indexing is reached only through
integration boundaries.

## Server-triggered path

`SourceService.RegisterSource`, `ListSources`, `TestConnection`,
`TriggerIngestion` and `GetIngestionStatus` are implemented in
`cce.sources.service`. The thin HTTP adapter exposes source listing as
`GET /sources`; source configuration is persisted by
`PostgresSourceRepository`; `TriggerIngestion` creates a durable ingestion run,
connects to the registered source, lists the available objects/schema and calls
`run_ingestion()`.

For unstructured sources, the service currently composes executable `local-fs`
and `azure-blob` connectors. For structured sources, it composes the existing
Snowflake connector and schema-card ingestion path.
An unstructured source may set `config.max_files` to a positive integer to cap
each manually triggered run. Azure Blob `config.prefix` is applied recursively
to all blob names beneath that virtual-directory prefix.
Connector construction and connection are inside the source worker's failure
boundary, so Azure configuration/authentication failures are logged and
persisted on the ingestion run as `FAILED`.

Unstructured document parsing is selected by MIME type through
`ParserFactory`: PDFs use `pypdfium2`, Word documents use `python-docx` and
PowerPoint decks use `python-pptx`. Each format is registered independently so
an unavailable optional parser dependency disables only that format.

## Index boundary

The ingestion workflow still emits one normalized payload through its SDK emit
hook. In server-triggered ingestion, that hook is supplied by the configured
AgenticPlane boundary implementation:

- `CCE_INDEX_BACKEND=local` uses the pgvector-backed
  `LocalIndexClient`.
- `CCE_INDEX_BACKEND=agentic_plane` uses the real SDK-backed
  `AgenticPlaneClient`. It sends raw chunks for server-side embedding and keeps
  returned memory IDs in the CCE-owned `cce_agentic_plane_memory` bridge table.

The local index remains the offline/dev fallback. Neither backend's ingestion
path implements graph extraction, governance proposal creation, package
assembly or approved runtime retrieval.
