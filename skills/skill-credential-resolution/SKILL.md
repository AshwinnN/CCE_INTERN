---
name: skill-credential-resolution
description: >-
  Resolves a credential_ref to a least-privilege credential lease across any
  registered secret backend — HashiCorp Vault, AWS Secrets Manager, GCP Secret
  Manager, Azure Key Vault or an internal store — returning an opaque lease that
  never carries secret material, or a REJECTED result citing the rule that
  blocked it. Activate when a credential_ref, secret reference, credential
  lease, service account, warehouse role or least-privilege grant must be
  resolved or re-verified before a connection is opened. Use the
  /resolve-credential command to emit a lease.
metadata:
  depends_on:
    - "skill-source-registry"
---

# Credential Resolution

## Purpose & Activation

Activate when a connect or sync skill holds a `credential_ref` and needs a
usable lease, for a structured or an unstructured source alike. Owned by the
CCE Ingestion Agent at author time and the Runtime Resolver at answer time.

- A connect skill must exchange a `credential_ref` for a lease.
- A role changed and an existing lease must be re-verified.
- A lease expired and the caller needs a fresh one.

## Commands

- `/resolve-credential` — validate a request and emit its lease using `scripts/resolve_credential.py`.

## Core Rules

1. **ALWAYS accept a `credential_ref` only, NEVER an inline secret in any field** (CRD01) — an inline secret ends up in a profile, a log and a git history.
2. **ALWAYS resolve through a registered backend scheme, NEVER a vendor conditional** (CRD02) — the backend is as swappable as the data source, and hardcoding one trades warehouse lock-in for secret-store lock-in.
3. **NEVER place secret material in the lease, in logs, or in any returned field** (CRD03) — the lease is an opaque handle; the secret is passed to the driver out of band and never serialized.
4. **ALWAYS REJECT a role carrying any write grant** (CRD04) — least privilege at the boundary is verified here, before the connect skill's write probe, not instead of it.
5. **ALWAYS require a bounded, positive TTL and REJECT an unbounded one** (CRD05) — a lease without expiry is a permanent credential wearing a temporary name.
6. **ALWAYS derive `lease_id` deterministically from the `credential_ref`** (CRD06) — a random id makes a TRACE record unreproducible on replay.
7. **ALWAYS return the identical lease field set for every backend** (CRD07) — callers must never branch on which secret store answered.

## Lease Contract

| Field | Notes |
|---|---|
| `lease_id` | `lse_<final ref segment>`, deterministic (CRD06) |
| `credential_ref` | echoed; the reference, never the value |
| `backend` | resolved scheme (`vault`, `aws-sm`, `gcp-sm`, `azure-kv`, `secret`) |
| `role` | the least-privilege role bound to this lease |
| `grants` | the read grants held, sorted |
| `grants_write` | always `false` on a READY lease (CRD04) |
| `ttl_seconds` | bounded and positive (CRD05) |
| `status` | `READY` or `REJECTED` |
| `violated_rule` | rule ID when REJECTED, else `null` |

No field carries secret material, by construction (CRD03).

## References

- [`references/backend-contract.md`](references/backend-contract.md) — the two methods a secret backend must implement, and how to register a new scheme.

## Checklist

- [ ] Only `credential_ref` accepted; every inline secret field rejected (CRD01)
- [ ] Backend resolved by scheme lookup; no vendor name in a conditional (CRD02)
- [ ] No secret material present in the lease or any log line (CRD03)
- [ ] Any write grant on the role rejected (CRD04)
- [ ] `ttl_seconds` present, positive and bounded (CRD05)
- [ ] `lease_id` equals `lse_<final ref segment>` (CRD06)
- [ ] Lease field set identical across all backends (CRD07)
- [ ] `scripts/resolve_credential.py` exits 0 on a lease, 1 on a rejection, printing the rule ID
