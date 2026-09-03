# Validation — Structured Source Connect

Eleven cases covering all ten Core Rules. Each input is a source profile;
each expected value is the literal ConnectionHandle the skill emits for it.

Coverage splits three ways:

- **Agnosticism** — four different adapters (Snowflake, Postgres, Databricks,
  BigQuery) run through the identical contract and produce the identical field
  set. If a future change makes one adapter's handle differ in shape, these
  four cases diverge together and the regression is obvious.
- **Rejections** — one case per rule that can block a connection, each
  asserting the rejection shape rather than just the failure.
- **Boundary** — an adapter that cannot prove read-only. It is registrable but
  never connectable, which is the point.

Run: `python3 scripts/validate_source_profile.py validation/test-data/<file>`.
Exit 0 means READY, exit 1 means REJECTED with the rule ID on stderr.

## A note on the fixture field

`_probe_write_succeeds` in TC-006 simulates a live write probe returning
"the write succeeded" without needing a real warehouse. It is a test fixture
only. A real adapter calls `probe_write(conn)`; the underscore prefix marks it
as never valid in a production profile, and it should be rejected outright once
profile schema validation lands.
