---
name: skill-strucutred_source_connect
description: >-
  Opens a governed, read-only connection to any registered structured data
  source and returns a normalized ConnectionHandle, or a REJECTED result
  citing the rule that blocked it. Adapter-agnostic: Snowflake, Postgres,
  Databricks, BigQuery and any adapter registered later resolve through the
  same contract. Activate when a source profile, connection profile,
  source_id, adapter, credential_ref or warehouse connection needs to be
  opened, re-opened or validated before schema discovery, sampling or query
  execution; also when a caller asks to connect to Snowflake, connect to the
  warehouse, or open a data source. Use the /connect-source command to
  validate a profile and emit its handle.
metadata:
  depends_on:
    - "skill-source-registry"
  input_adapters:
    - "common/registry_to_structured_connect.py"
  uses_internal_default_registry: true
---

# Structured Source Connect

## Purpose & Activation

Activate when a caller must open or re-validate a connection to a registered
structured source before any STR-02 discovery, STR-03 sampling or STR-08
execution runs. Owned by the CCE Ingestion Agent at author time and by the
Runtime Resolver at answer time.

- A source profile is supplied and a ConnectionHandle is needed.
- An existing handle must be re-verified after a credential or role change.
- A connection failed and the caller needs the rule ID that blocked it.

## Commands

- `/connect-source` — validate a source profile and emit its ConnectionHandle using `scripts/validate_source_profile.py`.

## Core Rules

1. **ALWAYS resolve the adapter through the source registry, NEVER by branching on a vendor name** (STR01) — a `if adapter == "snowflake"` in core is how the engine stops being source-agnostic.
2. **ALWAYS emit the same ConnectionHandle field set for every adapter** (STR02) — callers must never need to know which vendor answered.
3. **ALWAYS prove read-only with a live write probe before status READY, and REJECT any adapter that cannot probe** (STR03) — a profile claiming `read_only` is a claim, not evidence, and an unprovable source is rejected rather than trusted.
4. **NEVER accept an inline credential; resolve only through `credential_ref`** (STR04).
5. **ALWAYS bind `statement_timeout_ms` and `max_rows` at connect time, and REJECT a profile that omits either** (STR05) — per-query limits are skippable under pressure; connection-level limits are not.
6. **ALWAYS derive `handle_id` deterministically as `hnd_<source_id>`** (STR06) — a random UUID makes a TRACE record unreproducible across replays.
7. **NEVER fall back to another source or adapter when a connection fails** (STR07) — a silent fallback answers the question from the wrong warehouse.
8. **ALWAYS return `status: REJECTED` carrying the violated rule ID, NEVER a partially populated handle** (STR08).
9. **ALWAYS attach the dialect profile resolved by the dialect skill to the handle** (STR09) — downstream SQL generation and guarding read dialect from the handle, not from config.
10. **NEVER place schema, table or row content in the handle** (STR10) — connect is not discovery; that is STR-02 and STR-03.

## Workflow

1. Announce: "Opening governed connection to `<source_id>`…"
2. Load the source profile and reject unknown keys.
3. Resolve `adapter` against the source registry; on miss, REJECT (STR01).
4. Reject any profile carrying an inline credential field (STR04).
5. Reject any profile missing `statement_timeout_ms` or `max_rows` (STR05).
6. Reject any profile declaring a fallback source or adapter (STR07).
7. Resolve `credential_ref` from the secret store; never log the resolved value.
8. Open the connection under the declared least-privilege role.
9. Run the write probe; REJECT if the adapter cannot probe, or if the write succeeded (STR03).
10. Resolve the dialect profile and attach it (STR09).
11. Emit the normalized handle as `hnd_<source_id>` with `status: READY` (STR02, STR06), or a REJECTED result citing the first rule violated (STR08).

## Handle Contract

Field set is fixed across every adapter. Any adapter that cannot populate a
field returns `null` for it rather than omitting the key.

| Field | Notes |
|---|---|
| `handle_id` | `hnd_<source_id>` (STR06) |
| `source_id` | echoed from the profile |
| `adapter` | registry key, not a display name |
| `dialect` | resolved profile, not copied from config (STR09) |
| `read_only_verified` | write-probe result; always `true` on a READY handle (STR03) |
| `statement_timeout_ms`, `max_rows` | bound at connect (STR05) |
| `schema_scope` | names only, never contents (STR10) |
| `status` | `READY` or `REJECTED` |
| `violated_rule` | rule ID when REJECTED, else `null` (STR08) |

## References

- [`references/adapter-contract.md`](references/adapter-contract.md) — the four methods any new adapter must implement, and the registry entry shape.

## Checklist

- [ ] Adapter resolved via registry lookup; no vendor name appears in a conditional (STR01)
- [ ] Handle contains every contract field for every adapter, `null` where unsupported (STR02)
- [ ] Write probe executed; adapters that cannot probe are REJECTED, never READY (STR03)
- [ ] No inline credential field accepted; only `credential_ref` resolved (STR04)
- [ ] `statement_timeout_ms` and `max_rows` both present and bound (STR05)
- [ ] `handle_id` equals `hnd_<source_id>` (STR06)
- [ ] No fallback source or adapter honoured on failure (STR07)
- [ ] REJECTED results carry `violated_rule` and no partial handle fields (STR08)
- [ ] `dialect` populated from the dialect skill, not from the profile (STR09)
- [ ] Handle contains no schema, table or row content (STR10)
- [ ] `scripts/validate_source_profile.py` exits 0 on a valid profile, 1 on a rejected one, printing the rule ID
