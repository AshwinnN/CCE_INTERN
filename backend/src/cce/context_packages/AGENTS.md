# Context Packages Module Guide

## Status

**PLANNED**

Implemented scaffolding:
- dataclasses for package, glossary, policy rule, semantic mapping, verified SQL and ambiguity.
- approval assertion helper.
- basic dictionary override helper.
- patch-version increment helper.
- package service method shapes and protobuf contracts.

Missing:
- persistent package/version storage;
- assembly from approved assets;
- immutable version contents;
- active version selection;
- real scope hierarchy and precedence model;
- graph/ambiguity/SQL asset linkage;
- approval-driven version bump.

## Purpose

Target ownership: assemble and version domain-scoped, approved context assets and apply package/inheritance boundaries without hardcoding domain knowledge in the core.

## Does NOT Own

- deciding whether a proposal is approved (`governance/`)
- source extraction (`ingestion/`)
- runtime question reasoning (`runtime/`)
- transport mapping

## Entry Points

Current placeholders/helpers:
- `backend/src/cce/context_packages/service.py::ContextPackageService`
- `builder.py::assert_assets_approved()`
- `versioning.py::next_patch_version()`
- `inheritance.py::resolve_overrides()`

## Main Flow

### Current

```text
RPC/HTTP -> ContextPackageService -> [] / NOT_FOUND
```

No package is built or loaded.

### Target — not implemented

```text
APPROVED assets
  -> package scope selection
  -> compose glossary / semantic mappings / policy rules / verified SQL / graph / ambiguity
  -> immutable package version
  -> precedence/inheritance resolution
  -> active version available to runtime
```

## Important Components

`models/package.py::Package`
- lightweight package dataclass.

`models/{glossary,policy_rule,semantic_mapping,verified_sql,ambiguity}.py`
- target governed-asset shapes; data-only.

`builder.py`
- approval assertion only.

`inheritance.py`
- merges dict layers in argument order; no explicit GLOBAL/DOMAIN/REGION/ACCOUNT model.

`versioning.py`
- increments the patch component of a supplied version string.

`backend/migrations/cce_control/004_context.sql`
- schema-only placeholder.

## Inputs / Outputs

Target inputs:
- approved assets + scope + parent version

Target outputs:
- package ID/version + immutable asset membership + resolved package view

Current service returns placeholders.

## Dependencies

- `governance.policy.require_approved`

## Used By

- package RPC/HTTP adapters invoke placeholder service.
- runtime package resolver does not yet call the package service.

## Invariants

### Enforced

None on a live package path.

### Architectural Requirements

- package builder accepts approved assets only;
- domain/business knowledge remains in packages, not core code;
- versions are immutable and auditable;
- new approved delta creates a new package version rather than mutating an old one;
- intended precedence is Global < Domain < Regional < Account/customer;
- ambiguity information and verified SQL are versioned with the package.

## Modification Guide

Minimal implementation surface:
- `context_packages/service.py`
- builder/versioning/inheritance logic
- new `persistence/postgres/package_repository.py`
- `004_context.sql`
- package tests
- runtime package resolver only when retrieval is connected

Do not put package persistence in the structured metadata repository.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Package asset model | package model/repository/migration | runtime context assembler, proto | connectors |
| Versioning policy | versioning + repository/service | traceability, runtime | parser code |
| Scope precedence | inheritance/package resolver | runtime answers | source fetch |

## Do Not Inspect Unless Needed

Skip provider connectors, parser internals and source registry for package implementation. Inspect governance for approval semantics and runtime only for the consumer contract.

## Known Gaps / Architecture Mismatch

Expected:
- versioned domain package is the approved serving object.

Current:
- no package row/version/asset membership can be persisted or retrieved.

Status: **PLANNED**

Evidence:
- `context_packages/service.py`
- `backend/migrations/cce_control/004_context.sql`
