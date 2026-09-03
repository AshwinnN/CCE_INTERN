---
name: skill-document-source-connect
description: >-
  Opens a governed, read-only connection to any registered unstructured source
  and returns a normalized DocumentHandle, or a REJECTED result citing the rule
  that blocked it. Adapter-agnostic: Google Drive, Gmail, SharePoint, Slack,
  Confluence and any adapter registered later resolve through the same
  contract. Activate when a document source, drive, mailbox, workspace, channel,
  content store or object scope must be connected, re-connected or validated
  before document discovery, sync or ingestion runs; also when a caller asks to
  connect to Google Drive, connect to Gmail, or open a document source. Use the
  /connect-document-source command to validate a profile and emit its handle.
metadata:
  depends_on:
    - "skill-source-registry"
    - "skill-credential-resolution"
---

# Document Source Connect

## Purpose & Activation

Activate when a caller must open or re-validate a connection to a registered
unstructured source, ahead of any DOC-02 discovery or DOC-03 ingestion. Owned
by the CCE Ingestion Agent.

- A document source profile is supplied and a DocumentHandle is needed.
- An existing handle must be re-verified after an OAuth scope or role change.
- A connection failed and the caller needs the rule ID that blocked it.

## Commands

- `/connect-document-source` — validate a profile and emit its DocumentHandle using `scripts/validate_document_profile.py`.

## Core Rules

1. **ALWAYS resolve the adapter through the source registry, NEVER by branching on a vendor name** (DSC01) — the document path drifts from the structured path the moment one connector special-cases itself.
2. **ALWAYS emit the same DocumentHandle field set for every adapter** (DSC02) — a caller must not be able to tell a mailbox from a drive by the shape of its handle.
3. **ALWAYS prove read-only with a live write probe before status READY, and REJECT an adapter that cannot probe** (DSC03) — an OAuth token scoped for write can delete the contracts the engine exists to read; a declared scope is a claim, not evidence.
4. **NEVER accept an inline credential; resolve only through `credential_ref`** (DSC04).
5. **ALWAYS bind `fetch_timeout_ms` and `max_objects` at connect time, and REJECT a profile that omits either** (DSC05) — an unbounded crawl over a corporate drive is a denial of service against the source.
6. **ALWAYS derive `handle_id` deterministically as `hnd_<source_id>`** (DSC06) — a random id makes a TRACE record unreproducible on replay.
7. **NEVER fall back to another source or adapter when a connection fails** (DSC07) — a silent fallback grounds an answer in the wrong corpus.
8. **ALWAYS return `status: REJECTED` carrying the violated rule ID, NEVER a partially populated handle** (DSC08).
9. **ALWAYS verify entitlement capture is live before status READY, and REJECT an adapter that cannot read per-object ACLs** (DSC09) — documents carry per-object permissions that warehouse tables do not, and a corpus ingested without them leaks across permission boundaries at retrieval no matter what SEC-04 does later.
10. **NEVER place object content, titles or listings in the handle** (DSC10) — connect is not discovery; that is DOC-02 and DOC-03.

## Handle Contract

Field set is fixed across every adapter. An adapter that cannot populate a
field returns `null` rather than omitting the key.

| Field | Notes |
|---|---|
| `handle_id` | `hnd_<source_id>` (DSC06) |
| `source_id` | echoed from the profile |
| `adapter` | registry key, not a display name |
| `read_only_verified` | write-probe result; always `true` on a READY handle (DSC03) |
| `entitlement_capture_verified` | ACL-read result; always `true` on a READY handle (DSC09) |
| `fetch_timeout_ms`, `max_objects` | bound at connect (DSC05) |
| `object_scope` | scope identifiers only — folder, label or channel ids, never contents (DSC10) |
| `status` | `READY` or `REJECTED` |
| `violated_rule` | rule ID when REJECTED, else `null` |

## References

- [`references/adapter-contract.md`](references/adapter-contract.md) — the five methods any new document adapter must implement, and how object scope differs per source.

## Checklist

- [ ] Adapter resolved via registry lookup; no vendor name in a conditional (DSC01)
- [ ] Handle contains every contract field for every adapter (DSC02)
- [ ] Write probe executed; adapters that cannot probe are REJECTED (DSC03)
- [ ] No inline credential accepted; only `credential_ref` resolved (DSC04)
- [ ] `fetch_timeout_ms` and `max_objects` both present and bound (DSC05)
- [ ] `handle_id` equals `hnd_<source_id>` (DSC06)
- [ ] No fallback source or adapter honoured on failure (DSC07)
- [ ] REJECTED results carry `violated_rule` and no partial handle fields (DSC08)
- [ ] ACL read verified; adapters that cannot capture entitlements are REJECTED (DSC09)
- [ ] Handle contains no object content, titles or listings (DSC10)
- [ ] `scripts/validate_document_profile.py` exits 0 on a valid profile, 1 on a rejected one, printing the rule ID
