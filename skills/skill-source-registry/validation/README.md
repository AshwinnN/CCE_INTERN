# Validation — Source Registry

Twelve cases covering all eight Core Rules. Each input is a registry entry;
each expected value is the literal descriptor the skill emits for it.

Coverage splits three ways:

- **One registry, both kinds** — TC-001/002 register warehouses and TC-003/004
  register a drive and a mailbox, through the same code path, producing the
  same descriptor shape. If a future change makes structured and unstructured
  entries diverge, these four expecteds diverge with them.
- **Capability integrity** — a missing capability (TC-005) and a misspelled one
  (TC-006) are both rejected. The second matters more: a typo'd key would
  otherwise read as a silent `false` at the call site, and the capability it was
  meant to declare would never be enforced.
- **Registry hygiene** — reachability detail, dialect placement, schema version
  and key immutability.

Run: `python3 scripts/validate_registry_entry.py validation/test-data/<file>`.
Exit 0 means READY, exit 1 means REJECTED with the rule ID on stderr.
