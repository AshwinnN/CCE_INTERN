# Connector Agent

Durable, source-agnostic connector lifecycle and change-capture orchestrator.
It establishes and observes sources, then emits safe `SourceChangeEvent`
metadata for Ingest & Ground. It does not parse, chunk, embed, or otherwise
process changed content.

## Runtime Flow

```text
ConnectorAgent.handle(request)
 |
 +-- AdapterRegistryProvider.get(source_adapter)
 |
 +-- orchestrator.validate_registry_entry(entry)
 |
 +-- orchestrator.check_requested_capabilities(descriptor, requested)
 |
 +-- orchestrator.resolve_credential(credential_ref, role, grants, ttl)
 |
 +-- router.resolve_route(descriptor["kind"])
 |
 +-- kind == "structured"
 |     +-- common.registry_to_structured_connect.to_structured_connect_registry()
 |     +-- connectors.factory.ConnectorFactory.create(config).connect()
 |
 +-- kind == "unstructured"
 |     +-- common.registry_to_document_connect.validate_document_connect_registry()
 |     +-- orchestrator.connect_unstructured()
 |
 +-- observation.mode in {start, resume, poll}
       +-- StructuredChangeObserver:
       |     build schema card -> store version -> diff entities
       |
       +-- UnstructuredChangeObserver:
             validate listed object metadata -> map states to change events

       -> dedup
       -> hand off SourceChangeEvent(s)
       -> advance checkpoint only after successful handoff
```

## Deterministic Runtime

The connector-agent runtime does not load scripts from `skills/`. Registry
validation, credential prerequisites, source handles, schema-card creation,
and change diffs are implemented in Python code with explicit error codes.
The `skills/` tree can still exist as reference material, but runtime
connect/extract behavior must live behind connector abstractions.

The structured lane uses `connectors.base.StructuredConnector` and
`connectors.factory.ConnectorFactory`. Snowflake is the concrete
implementation today. Additional structured adapters should add a
`connectors/<adapter>/` package and register a connector class with the
factory.

The unstructured lane has a matching source abstraction in
`connectors.base.source.SourceConnector`. `connectors.generic_source`
contains a deterministic connector for integrations whose object listing and
fetching are provided by code.

## Extension Points

`AdapterRegistryProvider` is the source-registry boundary. The default
`StubAdapterRegistryProvider` is in-memory; a persistent registry can replace
it without changing `ConnectorAgent`.

`CheckpointStore` and `InMemoryDedupStore` are the observation state
boundaries. Production deployments should replace them with durable storage.

`object_lister` and `catalog_lister` are deterministic live-reader
functions. They are injected so tests can prove orchestration without network
credentials, while real deployments can bind them to provider clients.

## Out Of Scope

The connector agent never calls downstream content-processing logic:
document extraction, chunking, embeddings, fact extraction, graph upsert,
query generation, or guarded query execution. Those belong after
`SourceChangeEvent` handoff.
