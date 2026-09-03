# Validation — Credential Resolution

Eleven cases covering all seven Core Rules. Each input is a resolution request;
each expected value is the literal lease the skill issues for it.

Coverage splits three ways:

- **Backend agnosticism** — TC-001 through TC-004 run Vault, AWS Secrets
  Manager, GCP Secret Manager and Azure Key Vault through one path and produce
  an identical field set. A caller can never tell which store answered.
- **No secret material, ever** — no expected value in this suite contains a
  secret, because the lease has no field capable of carrying one. TC-010 covers
  a caller explicitly asking for one and being refused.
- **Least privilege** — a declared write grant (TC-007) and a blanket
  `ALL_PRIVILEGES` (TC-011) are both rejected.

TC-009 is the case worth reading twice: a TTL above the backend's ceiling is
**rejected, not clamped**. Clamping would hide a misconfiguration that then
persists; rejecting surfaces it once and it gets fixed.

Run: `python3 scripts/resolve_credential.py validation/test-data/<file>`.
Exit 0 means READY, exit 1 means REJECTED with the rule ID on stderr.
