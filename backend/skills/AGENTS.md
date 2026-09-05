# Agent Skills Guide

## Status

**PARTIAL**

Implemented:
- five versioned skill directories with `SKILL.md` and focused references/helpers:
  - `context_resolution`
  - `entity_resolution`
  - `semantic_mapping`
  - `policy_interpretation`
  - `sql_generation`
- dynamic Python loader functions in `backend/src/cce/skills/loader.py`.

Missing / incomplete:
- no production runtime/agent invokes these skills;
- skill loader comments/examples refer to older skill directory names that are not present;
- there is no skill registry/orchestration path selecting a skill based on runtime state.

## Purpose

Store reusable agent reasoning procedures and deterministic helper/reference assets. They are instructions/assets, not proof that the corresponding product capability is implemented.

## Does NOT Own

- deterministic security guards
- human approval
- database execution
- application orchestration
- persistence

## Entry Points

- `backend/src/cce/skills/loader.py::load_skill_function()`
- `backend/src/cce/skills/loader.py::load_skill_module()`

Current call-site scan found production code does not call the loader; tests do.

## Main Flow

### Current

```text
explicit test/caller -> load_skill_module()/load_skill_function() -> Python script asset
```

No production agent/runtime currently selects a SKILL.md or invokes the loader.

### Target — not implemented

```text
runtime/proposal agent state -> select declared skill -> load procedure/references/helpers -> agent reasoning -> typed candidate result
```

## Important Components

`context_resolution/SKILL.md`
- intended governed-context assembly procedure.

`entity_resolution/SKILL.md`
- intended entity-resolution procedure; deterministic rank helper in `backend/skills/entity_resolution/scripts/rank_candidates.py`.

`semantic_mapping/SKILL.md`
- intended business-to-physical mapping guidance.

`policy_interpretation/SKILL.md`
- intended policy/rule extraction guidance.

`sql_generation/SKILL.md`
- intended candidate SQL guidance; `backend/skills/sql_generation/scripts/validate_sql.py` is not the runtime security boundary.

## Inputs / Outputs

Current skill files are static assets. The loader can import script modules/functions by directory/name when explicitly invoked.

## Dependencies

No runtime orchestration dependency is wired.

## Used By

- tests.
- not used by production CCE services/runtime at this snapshot.

## Invariants

### Enforced

None at product-runtime level.

### Architectural Requirements — PARTIAL

- use agentic reasoning only for tasks that require it;
- keep security/approval decisions deterministic and external to skill prose;
- domain logic should come from package context, not be hardcoded into core prompts.

## Modification Guide

When changing a skill:
- keep procedure in `SKILL.md`;
- keep deterministic helpers in `scripts/`;
- keep long/static references in `references/`;
- add/update loader/runtime tests only when the skill is actually wired.

Do not claim a capability became IMPLEMENTED merely because a SKILL.md was added.

## Impact Map

| Change | Usually Modify | Potentially Impacted | Normally Unrelated |
|---|---|---|---|
| Skill procedure text | one `SKILL.md` | future agent behavior/tests | migrations |
| Deterministic helper | skill `scripts/` + tests | future agent invoking skill | RPC transport |
| Loader contract | `backend/src/cce/skills/loader.py` | all wired skills | provider SDKs |

## Do Not Inspect Unless Needed

Skill text changes normally do not require provider connectors, migrations, or transport handlers unless you are wiring that skill into a real runtime path.

## Known Gaps / Architecture Mismatch

Expected:
- runtime agents select/use versioned skills for entity resolution, policy interpretation, semantic mapping, context resolution and SQL generation.

Current:
- these are disconnected assets; current `runtime/` helpers remain placeholders.

Status: **PARTIAL assets / PLANNED runtime use**
