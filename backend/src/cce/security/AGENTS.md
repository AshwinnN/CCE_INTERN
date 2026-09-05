# Security Module Guide

## Status

**PARTIAL**

Implemented:
- `env://` and `azure-kv://` secret reference resolution.
- Snowflake private-key/passphrase credential resolution helper.
- entitlement and role decision helper functions.
- DLP call interface used by ingestion.

Missing / incomplete:
- real DLP/PII classification/redaction;
- entitlement capture/enforcement in retrieval/runtime;
- API authentication/authorization integration;
- consistent secret-reference dereferencing in provider environment builders.

## Purpose

Own reusable security boundaries: secret resolution, DLP/PII, entitlements and roles.

## Does NOT Own

- provider-specific query semantics
- governance lifecycle status
- package/domain rules
- transport response mapping

## Entry Points

- `backend/src/cce/security/credentials.py::load_credential()`
- `load_snowflake_keypair_credential()`
- `security/dlp.py::{classify_text, redact_text}`
- `security/entitlements.py::assert_entitled()`
- `security/roles.py::has_role()`

## Main Flow

Credential reference:

```text
env://NAME -> os.environ[NAME]
azure-kv://vault/secret -> DefaultAzureCredential -> SecretClient.get_secret()
```

Ingestion DLP:

```text
canonical text -> classify_text() -> optional redact_text()
```

Current DLP always returns PUBLIC; redaction is unchanged passthrough.

## Important Components

`credentials.py`
- parses and resolves `env://` and `azure-kv://` references.
- assembles Snowflake key-pair material and optional passphrase.

`dlp.py`
- stable DLP interface, explicitly stubbed.

`entitlements.py` / `roles.py`
- deterministic allow/role helpers; not wired into request/runtime paths.

## Inputs / Outputs

Inputs:
- credential reference strings; text/column labels; boolean entitlement state; actor roles.

Outputs:
- resolved secret text/key-pair material; DLP verdict/redacted text; allow/deny decisions.

## Dependencies

- Azure Identity / Key Vault Secrets SDK
- environment variables

## Used By

- Snowflake connector credential loading.
- ingestion DLP nodes.
- role/entitlement helpers currently have no verified production consumers.

## Invariants

### Enforced

- unsupported/malformed credential reference schemes fail rather than silently expose a different secret source.

### Architectural Requirements — PARTIAL

- DLP/PII must run before candidate knowledge: hook is present, behavior is not.
- entitlements must be enforced at retrieval: no active retrieval path.
- caller authentication/authorization must protect APIs: gRPC interceptor files are empty and HTTP has no equivalent security layer.

## Modification Guide

### Credential support

Usually modify:
- `security/credentials.py`
- provider config builder only to pass references correctly, not to duplicate secret fetch logic

### DLP

Usually modify:
- `security/dlp.py`
- ingestion tests around classify/redact behavior

Do not mix human governance approval with security classification.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| secret scheme | credentials resolver | connector config/bootstrap | package versioning |
| DLP classifier | `dlp.py` | ingestion emitted content | SQL proof |
| entitlement policy | `entitlements.py` + runtime retrieval/auth | MCP/UI through shared runtime | parser choice |

## Do Not Inspect Unless Needed

Skip package models and parser internals for credential changes. For authorization, inspect transports plus the shared actor/core model.

## Known Gaps / Architecture Mismatch

Expected:
- `.env.example` `azure-kv://...` values are resolvable through provider paths.

Current:
- Snowflake `build_config_from_env()` wraps the `CCE_SNOWFLAKE_PRIVATE_KEY` variable as `env://CCE_SNOWFLAKE_PRIVATE_KEY`; if that variable itself contains `azure-kv://...`, the resolved value becomes the reference string, not the PEM. Azure Blob fetch helpers also expect a raw connection string.

Status: **PARTIAL**
