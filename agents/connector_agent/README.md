# Connector Agent

Durable, source-agnostic connector lifecycle and change-capture orchestrator.
Establishes and observes a source; never reads or processes the content of
what changed. Everything past "here is a safe `SourceChangeEvent`" belongs to
Ingest & Ground, a later stage this Agent does not implement.

## Call graph

```
ConnectorAgent.handle(request)
 |
 +-- common.known_adapters.StubAdapterRegistryProvider.get(source_adapter)
 |     (MVP stub -- no persistent registry service exists yet)
 |
 +-- skill-source-registry :: validate(entry)                 [always]
 |     fail-closed: REGISTRY_KIND_MISMATCH / _CAPABILITIES_INVALID /
 |                  _DIALECT_MISSING / _SCHEMA_UNSUPPORTED / _DEPRECATED
 |
 +-- orchestrator.check_requested_capabilities(descriptor, ...)  [always]
 |     Agent-level check, not a Skill -- no existing Skill owns this.
 |
 +-- skill-credential-resolution :: resolve(request)           [always]
 |     fail-closed: CREDENTIAL_REF_MISSING / _RESOLUTION_FAILED
 |
 +-- router.resolve_route(descriptor["kind"])                  [always]
 |     branches ONLY on kind -- never on adapter/vendor name
 |
 +-- kind == "structured"
 |     +-- common.registry_to_structured_connect.to_structured_connect_registry(descriptor)
 |     +-- connectors.factory.ConnectorFactory.create(config).connect()   [NOT a skill -- see below]
 |         real, live write-probe; connection closed immediately after proving read-only
 |
 +-- kind == "unstructured"
 |     +-- common.registry_to_document_connect.validate_document_connect_registry(descriptor)
 |     +-- skill-document-source-connect :: validate(profile)
 |
 +-- observation.mode in {start, resume, poll}                 [optional]
       +-- kind == "structured"  -> StructuredChangeObserver
       |     +-- skill-dialect-profile :: resolve(request)
       |     +-- skill-sql-guard :: guard(request)  [intent="introspection", SQG08]
       |     +-- skill-schema-discovery :: build(request)           [_catalog stub]
       |     +-- skill-source-metadata-store :: do_retrieve / do_store
       |     +-- skill-source-sync :: sync(request)  [detection_strategy=card_diff]
       |
       +-- kind == "unstructured" -> UnstructuredChangeObserver
             +-- skill-document-sync :: sync(request)          [_objects stub]

       -> dedup (common.checkpoint_store.InMemoryDedupStore)
       -> hand off SourceChangeEvent(s)
       -> ONLY THEN advance checkpoint (common.checkpoint_store.InMemoryCheckpointStore)
```

## Request / response / event contracts

See `contracts.py`. Field names follow the real skill contracts where the
design prompt's illustrative examples didn't match them (documented inline
and in the decision log below) -- most notably capability names, which are
`write_probe` / `statement_timeout` / `row_cap` / `schema_scope` (structured)
and `write_probe` / `change_detection` / `entitlement_capture` /
`content_fetch` / `incremental_sync` (unstructured), taken from
`skill-source-registry`'s actual `CAPABILITY_SETS`, not the prompt's
`"connect"` / `"read_only"` placeholders.

## The structured lane's connect step is a tool, not a skill

`connect_structured()` (orchestrator.py) no longer calls
`skill-strucutred_source_connect`. That skill's write-probe was a
caller-supplied boolean (`_probe_write_succeeds`) that production code
never actually set, so its "prove read-only with a live write probe"
guarantee was simulated, never enforced end to end. Opening a database
connection is a deterministic process with a real, checkable outcome --
it now lives in `connectors/` (see `structured_connector_architecture.md`)
as `connectors.factory.ConnectorFactory.create(config).connect()`, which
opens a real connection and runs a real `CREATE TEMPORARY TABLE` probe
before returning. The connection is closed immediately after proving
read-only -- this Agent still only ever hands back an opaque `handle_id`,
never a live session (see `contracts.ConnectorResponse.to_dict()`, which
must stay JSON-serializable). `ConnectorAgent(structured_connector_factory=...)`
lets a caller (or a test) inject a fake `StructuredConnector`, the same
convention `object_lister`/`catalog_lister` already establish for the
other two live-driver touchpoints -- see
`tests/connector_agent/test_connector_agent.py::FakeStructuredConnector`.
`skill-strucutred_source_connect` itself still exists on disk as
documentation but is invoked nowhere in this Agent.

## Skills actually invoked, and why

| Skill | Why required |
|---|---|
| `skill-source-registry` | Fail-closed validation of the adapter descriptor before any routing decision. |
| `skill-credential-resolution` | Credential prerequisite; the Agent never handles a raw secret. |
| `skill-document-source-connect` | Opens the unstructured lane's connection handle. |
| `skill-document-sync` | Unstructured change detection (cursor pull), self-contained. |
| `skill-schema-discovery` | Structured lane's fresh card, required by `skill-source-sync`'s own `card_diff` strategy. |
| `skill-source-metadata-store` | Structured lane's stored card to diff against -- also required by `skill-source-sync`. |
| `skill-source-sync` | Structured change detection (card diff), classifies added/changed/removed and breaking changes. |
| `skill-dialect-profile` | Resolves the full dialect profile (`row_limit_strategy`, `system_catalogs`, `forbidden_keywords`) `skill-sql-guard` needs to clear the introspection query. Added once `skill-sql-guard` existed to call it for real -- previously excluded because nothing actually invoked it. |
| `skill-sql-guard` | Clears schema-discovery's introspection SQL per SCD06, using the `intent: "introspection"` carve-out (SQG08) added to resolve a real conflict with SQG05 -- see "Known gaps" below. |

## Skills explicitly excluded

| Skill | Why excluded |
|---|---|
| `skill-provenance-capture` | Its contract requires `chunk_id` + span, which don't exist for a connector-level change event. Using it here would mean inventing fake values. |
| `skill-document-content-extraction`, `skill-document-chunking`, `skill-source-normalization`, `skill-embedding-generation`, `skill-fact-extraction`, `skill-entity-relationship-extraction`, `skill-knowledge-graph-upsert`, `skill-candidate-query-generation`, `skill-guarded-query-execution` | Downstream content processing / governance / query execution -- explicitly out of scope. Asserted never-loaded by `tests/connector_agent/test_connector_agent.py::ForbiddenSkillTests`. |

## Known gaps, flagged rather than papered over

1. **No registry persistence service exists.** `common/known_adapters.py` is
   an explicitly marked MVP stub behind `AdapterRegistryProvider` -- swap the
   implementation, not the Agent, when a real one exists.
2. **No generic checkpoint/cursor persistence skill exists.**
   `skill-source-metadata-store` only stores schema cards. `common/checkpoint_store.py`
   is Agent-owned state for exactly this reason, behind a swappable interface.
3. **Resolved:** `skill-sql-guard` now exists and is genuinely wired into
   `StructuredChangeObserver` -- but wiring it surfaced a real contract
   conflict, not just a missing file. SQG05 unconditionally blocked any SQL
   referencing a `system_catalogs` namespace, and introspection SQL reads
   exactly those namespaces by definition (traced through the actual regex
   against a real introspection query -- it matched). Resolved by adding
   SQG08: an explicit, narrow `intent: "introspection"` carve-out that lifts
   *only* SQG05, never SQG02/03/04/06 (verified by
   `tests/test_sql_guard_regression.py`). This is a trust boundary the guard
   itself cannot enforce -- `StructuredChangeObserver` is the only code path
   in this Agent ever allowed to set it, and that discipline is enforced by
   not wiring the value in anywhere else, not by the guard.
4. **Two more pre-existing stale `depends_on` references surfaced** while
   inspecting the newly-added skills, unrelated to this Agent's own code:
   `skill-guarded-query-execution` and `skill-schema-discovery` both name
   `skill-structured-source-connect` (hyphenated) instead of the real
   `skill-strucutred_source_connect`. Documented in
   `tests/test_skill_metadata.py`'s pre-existing-issue baseline, not fixed --
   both skills are outside this Agent's four owned connector-stage skills.
5. **Change detection still has no real source driver.** Every "live" fact
   used for *detecting what changed* (`_objects`, `_catalog`) is injected
   via caller-supplied `object_lister` / `catalog_lister` callables,
   matching the fixture convention every Skill in this repo already uses.
   Wiring an actual Google Drive/Slack driver behind `object_lister` is a
   separate, later task. **Resolved for the structured lane's connect
   step**, though: `connectors.snowflake.SnowflakeConnector` is a real
   driver with a real write-probe (see the section above) -- the gap that
   remains is everything else change-detection related, not connecting.
