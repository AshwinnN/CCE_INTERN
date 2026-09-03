# Adapter Contract

What a new structured-source adapter must implement to be registrable. Adding
an adapter must never require an edit to the connect skill itself — if it
does, the adapter is leaking vendor knowledge upward and STR01 is broken.

## Registry entry

```json
{
  "adapter": "snowflake",
  "dialect": "snowflake",
  "module": "cce.adapters.snowflake",
  "supports": {
    "write_probe": true,
    "statement_timeout": true,
    "row_cap": true,
    "schema_scope": true
  }
}
```

`adapter` is the registry key used in a source profile. It is an identifier,
never a display string, and is never renamed after first use — profiles,
handles and TRACE records all reference it.

## Required methods

| Method | Returns | Notes |
|---|---|---|
| `open(profile, secret)` | native connection | Must bind the least-privilege role declared in the profile. Must not retry against a different role. |
| `probe_write(conn)` | `bool` | Attempts a write the adapter expects to fail. Returns `True` only if the write **succeeded** — i.e. the source is not read-only. The connect skill REJECTS on `True` (STR03). |
| `bind_limits(conn, timeout_ms, max_rows)` | `None` | Applies both at session level. Raise if the source cannot enforce either — a silently unenforced limit is worse than a rejection (STR05). |
| `close(conn)` | `None` | Idempotent. |

## Capability gaps

`write_probe` is **not optional**. An adapter declaring `"write_probe": false`
is registrable but every connect against it is REJECTED under STR03 — read-only
is a security boundary, and a source that cannot demonstrate it is refused
rather than trusted on configuration alone.

For the remaining capabilities, an adapter that cannot support one declares
`false` and the connect skill records `null` in the corresponding handle field
rather than omitting the key (STR02). It does **not** substitute an
application-side emulation — a row cap enforced in Python after the warehouse
has already returned ten million rows is not a row cap.

## Adding an adapter

1. Implement the four methods above.
2. Add the registry entry.
3. Add a valid-profile test case and a rejection test case to the connect
   skill's `validation/test-suite.json`.
4. Add the dialect entry to the dialect-profile skill.

No step in this list edits `SKILL.md`.
