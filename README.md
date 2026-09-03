# CCE Tool — Production MVP Solution Package

This is the review/build package for the CoStrategix Context Engine (CCE).

The folder is intentionally organized so Antigravity can use the repository itself as the source of truth.

## Source-of-truth order

1. `docs/specs/01-business-spec.md`
2. `docs/specs/02-design-spec.md`
3. `docs/specs/03-technical-spec.md`
4. `skills/*/SKILL.md`
5. `agent/Agent.md`
6. `docs/governance/DECISIONS.md`

## Main folders

```text
CCE-Tool/
├── README.md
├── AGENTS.md
├── .antigravity/
│   └── build-prompt.md
├── docs/
│   ├── specs/
│   ├── governance/
│   └── review/
├── skills/
│   ├── skill-cce-connector-adapter/
│   ├── skill-cce-ingest-ground/
│   ├── skill-cce-entity-resolution/
│   ├── skill-cce-ambiguity-resolution/
│   ├── skill-cce-governance/
│   ├── skill-cce-context-package/
│   ├── skill-cce-context-assembly/
│   ├── skill-cce-governed-query/
│   ├── skill-cce-proof-evaluation/
│   ├── skill-cce-lineage-observability/
│   ├── skill-cce-mcp-broker/
│   └── skill-cce-package-validation/
├── agent/
│   └── Agent.md
└── prompts/
    └── ANTIGRAVITY_CCE_BUILD_PROMPT.md
```

## Important

This package contains the product-definition artifacts. It is not the application implementation yet.

Antigravity should create the implementation under a separate application structure such as:

```text
src/
tests/
migrations/
deploy/
scripts/
```

Do not move Specs or Skills into application source code. They are build contracts.

## MVP

The first concrete adapters are:
- Snowflake
- Google Docs

The CCE core must remain:
- domain agnostic
- source agnostic
- model/provider agnostic
- storage agnostic through ports
- agent-framework agnostic

The initial graph/context store is ArcadeDB behind an adapter boundary.

React is intentionally excluded from this repository's implementation scope. It will consume the CCE REST/API layer later.
