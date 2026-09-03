# Capability Sets

Every registry entry declares the exact capability set for its `kind`. Sets are
closed — an entry declaring fewer keys is rejected (REG03), and one declaring an
unrecognized key is rejected too (REG04). Both rejections exist because a missing
key and a `false` key are indistinguishable at the call site, and the caller will
read the missing one as "unsupported, carry on".

## kind: structured

Warehouses, lakehouses and relational databases.

| Capability | Means |
|---|---|
| `write_probe` | The adapter can attempt a write it expects to fail, proving read-only. Declaring `false` makes every connect REJECT under the connect skill's STR03 — read-only is a boundary, not a configuration claim. |
| `statement_timeout` | A session-level statement timeout can be bound at connect. |
| `row_cap` | A result row cap can be enforced by the source, not emulated after the rows have already crossed the wire. |
| `schema_scope` | Discovery can be restricted to named schemas rather than the whole instance. |

## kind: unstructured

Mailboxes, drives, document stores and chat archives.

| Capability | Means |
|---|---|
| `write_probe` | The adapter can attempt a write it expects to fail, proving read-only. Required for document sources exactly as for warehouses — an OAuth token scoped for write on a drive or mailbox can delete the customer contracts the engine is meant to read. |
| `change_detection` | The source can report what changed since a cursor, without a full re-scan. |
| `entitlement_capture` | Per-object ACLs can be read at ingestion, so SEC-03 and SEC-04 have something to enforce. |
| `content_fetch` | Object content can be read, not just its metadata listing. |
| `incremental_sync` | A partial sync can resume from a stored cursor after interruption. |

## Adding an adapter

1. Write the entry with the exact capability set for its kind.
2. For a structured adapter, add its dialect to the dialect-profile skill.
3. Add a valid-entry test case and one rejection case to `validation/test-suite.json`.

No step edits `SKILL.md` or the validator. If adding an adapter requires either,
vendor knowledge has leaked out of the data and REG01 is broken.

## Superseding an adapter

Keys are immutable (REG07). To replace one, register the new key and set
`deprecated: true` on the old entry. The old entry stays resolvable — TRACE
records from prior answers still reference it, and a replay that cannot resolve
its adapter is an unauditable answer.
