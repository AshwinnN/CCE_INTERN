# Document Adapter Contract

Mirrors the structured adapter contract. Adding an adapter must never edit the
connect skill itself - if it does, vendor knowledge has leaked upward and DSC01
is broken.

## Required methods

| Method | Returns | Notes |
|---|---|---|
| `open(profile, lease)` | native client | Binds the least-privilege scope named in the profile. |
| `probe_write(client)` | `bool` | Attempts a write it expects to fail. Returns `True` when the write **succeeded** - i.e. not read-only. Connect REJECTS on `True` (DSC03). |
| `read_acl(client, object_id)` | `list` | Per-object entitlements. An adapter that cannot do this is registrable but never connectable (DSC09). |
| `bind_limits(client, timeout_ms, max_objects)` | `None` | Applies both. Raise if unenforceable. |
| `close(client)` | `None` | Idempotent. |

## Why entitlement capture is a connect-time boundary

A warehouse table has one permission set. A drive has one *per object* - and the
contract in a folder a user cannot see is still readable by the connector's
service account.

If ACLs are not captured at ingestion, there is nothing for SEC-04 to enforce at
retrieval, and the knowledge base answers every user from the union of all
documents. That is not a bug that surfaces in testing; it surfaces when someone
asks a question and gets an answer sourced from a document they were never meant
to see.

So DSC09 refuses the connection outright rather than proceeding with entitlement
capture disabled. `public-bucket` is registered in the reference implementation
precisely to make that refusal testable.

## OAuth scopes are claims, not evidence

`drive.readonly` in a token request is a claim about what was asked for, not
proof of what was granted - tokens get re-issued, scopes get widened, and admin
consent can grant more than requested. DSC03 probes rather than reads the scope
string, for the same reason the structured connector probes rather than trusting
`read_only: true` in a profile.
