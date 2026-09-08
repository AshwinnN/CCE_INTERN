# Observability Module Guide

## Status

**PARTIAL**

Implemented:
- environment-driven log-level constant (`CCE_LOG_LEVEL`).
- `configure_logging()`: root logger with a console handler and a rotating
  file handler under `<repo root>/logs/` (gitignored), both formatted with
  the emitting file's path relative to the repo root, line number and
  function name.
- wired into `cce.main` at process startup, before the rest of the app is
  imported.
- domain-level logging at each ingestion stage (connect, list, extract,
  paginate, send-to-index), added directly in the boundary modules rather
  than here: `sources/service.py`, `connectors/structured/snowflake/
  connector.py`, `connectors/unstructured/azure_blob/connector.py`,
  `ingestion/orchestrator.py`, `integrations/agentic_plane/client.py`. A
  blanket per-function-call tracer (`sys.setprofile` over every call in the
  package) was tried and dropped — it produced call-graph noise with no
  domain meaning, which is the opposite of what ingestion traceability
  needs. Only counts/ids are logged, never row/document content or
  credentials.

Missing:
- meaningful metrics exporter/backend;
- distributed tracing/span implementation (`tracing.py` is still a
  placeholder);
- Langfuse/OpenTelemetry/event-stream behavior described by target product
  material;
- standalone scripts under `scripts/` are not wired (only the `cce.main`
  server entry point calls `configure_logging()`); call it from a script's
  own entry point if needed.

## Purpose

Own engineering diagnostics: logs, metrics and tracing. Do not use this module as the governance/audit record.

## Does NOT Own

- source/answer lineage
- approval history
- package/rule provenance

Those belong in `traceability/` and audit persistence.

## Entry Points

- `observability/logging.py::configure_logging()`
- `observability/metrics.py::increment()` — no-op
- `observability/tracing.py::current_span()` — returns `None`

## Main Flow

### Current

```text
cce.main (process start) -> configure_logging(LOG_LEVEL) -> root logger gets
    console + rotating-file (logs/cce.log) handlers
sources.service / connectors / ingestion.orchestrator / agentic_plane.client
    -> logging.getLogger(__name__).info(...) at each real pipeline step
metrics.increment(...) -> no-op
tracing.current_span() -> None
```

## Important Components

`config.py`
- `LOG_LEVEL` from `CCE_LOG_LEVEL`.

`logging.py`
- basic logging configuration helper.

`metrics.py` / `tracing.py`
- explicit placeholder functions.

## Inputs / Outputs

Inputs:
- log level and future metric/span events.

Outputs:
- current logging configuration only; metrics/tracing produce no backend data.

## Dependencies

Python standard logging only in current implementation.

## Used By

No verified production caller found for the helper functions.

## Invariants

### Enforced

No product invariant is enforced through observability.

### Architectural Requirements

- engineering telemetry remains separate from governance/audit semantics;
- runtime/ingestion should emit useful diagnostics without making logs the source of truth for traceability.

## Modification Guide

Add exporters/instrumentation here, then call them from composition/service boundaries. Do not write governance records into generic metrics/logs.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Log setup | observability logging + bootstrap/main wiring | all server diagnostics | governance state |
| Metrics exporter | metrics + service/workflow instrumentation | deployment config | package semantics |
| Tracing | tracing + boundary instrumentation | RPC/ingestion/runtime diagnostics | parser model |

## Do Not Inspect Unless Needed

Skip package/governance internals for ordinary instrumentation changes; consume stable IDs/events at boundaries.

## Known Gaps / Architecture Mismatch

Expected:
- operational telemetry for token usage, latency, query cost and workflow behavior.

Current:
- metrics/tracing are placeholders.

Status: **PARTIAL**
