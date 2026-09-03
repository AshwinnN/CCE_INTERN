---
name: skill-source-registry
description: >-
  Validates and resolves source adapter entries for every data source CCE can
  connect to, structured and unstructured alike, returning a normalized adapter
  descriptor or a REJECTED result citing the rule that blocked it. One registry
  serves warehouses and document stores through one entry shape. Activate when
  an adapter, adapter key, source registry entry, capability declaration or
  source_id must be registered, validated or resolved before a connection is
  opened; also when adding support for a new warehouse, lakehouse, mailbox,
  drive or document store. Use the /register-source command to validate an
  entry and emit its descriptor.
---

# Source Registry

## Purpose & Activation

Activate when an adapter descriptor must be resolved or a new registry entry
validated, ahead of any connect, discovery or sync skill running. Owned by the
CCE Ingestion Agent at author time and by the Runtime Resolver at answer time.

- A connect skill needs the descriptor behind an adapter key.
- A new adapter is being registered and its capability declaration checked.
- An entry changed and must be re-validated before activation.

## Commands

- `/register-source` — validate a registry entry and emit its descriptor using `scripts/validate_registry_entry.py`.

## Core Rules

1. **ALWAYS resolve an adapter by registry key lookup, NEVER by a vendor-name conditional** (REG01) — one `if adapter == "snowflake"` anywhere upstream and the engine stops being source-agnostic.
2. **ALWAYS serve structured and unstructured sources from one registry, discriminated by `kind`** (REG02) — two registries drift, and the second connector path silently grows its own conventions.
3. **ALWAYS require the exact capability set declared for that `kind`, and REJECT a partial declaration** (REG03) — an absent capability key is indistinguishable from an unsupported one.
4. **NEVER accept an unrecognized capability key** (REG04) — a typo becomes a silently-false capability, which is how a guard gets skipped.
5. **NEVER place credential, host, account or connection detail in a registry entry** (REG05) — the registry describes what an adapter can do, never how to reach an instance of it.
6. **ALWAYS set `dialect` on a structured entry and `null` on an unstructured one** (REG06).
7. **NEVER rename, reuse or replace an adapter key once registered** (REG07) — profiles, handles and TRACE records all reference it; supersede by registering a new key and marking the old one deprecated.
8. **ALWAYS carry `schema_version` on every entry** (REG08).

## Descriptor Contract

Field set is identical for both kinds. A field that does not apply to a kind is
`null`, never omitted.

| Field | Notes |
|---|---|
| `adapter` | registry key; immutable after registration (REG07) |
| `kind` | `structured` or `unstructured` (REG02) |
| `dialect` | set for structured, `null` for unstructured (REG06) |
| `capabilities` | exact set for the kind, all booleans (REG03, REG04) |
| `schema_version` | entry schema version (REG08) |
| `deprecated` | `true` when superseded; still resolvable for replay |
| `status` | `READY` or `REJECTED` |
| `violated_rule` | rule ID when REJECTED, else `null` |

## References

- [`references/capability-sets.md`](references/capability-sets.md) — the exact capability keys for each kind, and how to add a new adapter.

## Checklist

- [ ] Adapter resolved by key lookup only; no vendor name in a conditional (REG01)
- [ ] Structured and unstructured entries validated by the same code path (REG02)
- [ ] Exact capability set present for the declared kind (REG03)
- [ ] Unrecognized capability keys rejected, not ignored (REG04)
- [ ] No credential, host or account field accepted in an entry (REG05)
- [ ] `dialect` set for structured, `null` for unstructured (REG06)
- [ ] No entry replaces or renames an existing adapter key (REG07)
- [ ] `schema_version` present (REG08)
- [ ] `scripts/validate_registry_entry.py` exits 0 on a valid entry, 1 on a rejected one, printing the rule ID
