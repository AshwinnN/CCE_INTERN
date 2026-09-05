# Observability Module Guide

## Status

**PARTIAL**

Implemented:
- environment-driven log-level constant.
- `configure_logging()` wrapper around `logging.basicConfig()`.

Missing:
- meaningful metrics exporter/backend;
- distributed tracing/span implementation;
- verified startup wiring for logging helper;
- Langfuse/OpenTelemetry/event-stream behavior described by target product material.

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
optional caller -> configure_logging(level) -> logging.basicConfig
metrics.increment(...) -> no-op
tracing.current_span() -> None
```

No verified startup wiring calls these helpers.

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
