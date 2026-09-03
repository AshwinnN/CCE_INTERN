# Backend Contract

A secret backend is as swappable as a data source. Hardcoding one trades
warehouse lock-in for secret-store lock-in, which is the same mistake in a
less obvious place (CRD02).

## Registry entry

```json
{
  "scheme": "vault",
  "name": "hashicorp-vault",
  "module": "cce.secrets.vault",
  "max_ttl_seconds": 3600
}
```

`scheme` is the prefix of a `credential_ref` — `vault://cce/wh_prod` resolves
to the `vault` backend. It is an identifier, never a display string, and is
never renamed after first use.

## Required methods

| Method | Returns | Notes |
|---|---|---|
| `fetch(ref, ttl_seconds)` | driver-native credential | Hands the secret **directly to the connection driver**. Must not return it to the caller, log it, or place it in the lease (CRD03). |
| `describe_grants(ref)` | `list[str]` | The grants the credential's role actually holds, read from the source of truth — not copied from the request. |

## Why grants are read, not declared

`describe_grants` exists because a request declaring `["SELECT"]` is a claim
about a role, not evidence about it. The same reasoning drives the connect
skill's write probe: configuration says what someone intended, the system says
what is true. This skill rejects a *declared* write grant early and cheaply;
the write probe catches an *undeclared* one later and definitively. Both are
needed — neither replaces the other.

## TTL ceilings

Each backend declares its own `max_ttl_seconds`, and a request exceeding it is
rejected rather than silently clamped (CRD05). Clamping hides a
misconfiguration that would otherwise be fixed once; rejecting surfaces it.

## Adding a backend

1. Implement `fetch` and `describe_grants`.
2. Add the registry entry with its TTL ceiling.
3. Add a valid-lease test case to `validation/test-suite.json`, asserting the
   lease shape is identical to every other backend's.

No step edits `SKILL.md` or the resolver.
