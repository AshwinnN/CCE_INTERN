# Ingestion Flow

Structured and unstructured ingestion are coordinated by
`cce.ingestion.orchestrator`; AgenticPlane indexing is reached only through
integration boundaries.

## Server-triggered path

`SourceService.RegisterSource`, `TestConnection`, `TriggerIngestion` and
`GetIngestionStatus` are implemented in `cce.sources.service` and reached by
both gRPC and the thin HTTP adapter. Source configuration is persisted by
`PostgresSourceRepository`; `TriggerIngestion` creates a durable ingestion run,
connects to the registered source, lists the available objects/schema and calls
`run_ingestion()`.

For unstructured sources, the service currently composes executable `local-fs`
and `azure-blob` connectors. For structured sources, it composes the existing
Snowflake connector and schema-card ingestion path.

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
- `CCE_INDEX_BACKEND=agentic_plane` uses `AgenticPlaneClient`; the external SDK
  implementation remains a placeholder.

The local index is for MVP/demo searchability and synthetic end-to-end proof. It
does not implement graph extraction, governance proposal creation, package
assembly or approved runtime retrieval.
