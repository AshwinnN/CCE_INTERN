# Governance and package lifecycle

PostgreSQL is authoritative for proposals, human review, asset revisions, evidence, approved relational graph projections, package manifests and snapshots. AgenticPlane is candidate evidence infrastructure.

Only a SUCCESS ingestion run can create a proposal batch (PARTIAL/FAILED runs never do). Each Workspace progresses independently after that shared completion gate. Proposals use `PROPOSED`, `APPROVED`, or `REJECTED`; REVIEW is an action, not persisted state.

Stewards can edit the typed `reviewed_payload` while the immutable `machine_payload` preserves the original extraction. Edits cannot change the asset type/canonical identity. Every edit/approve/reject writes an append-only review action with the actor and payload artifacts. Workspace creation requires ADMIN; decisions require STEWARD. The application currently trusts supplied actor claims and requires an authenticated upstream boundary in deployment; it does not implement an identity provider.

The last terminal decision automatically invokes `PackageBuilder` inside the same Workspace-locked transaction. There is no manual publish call. Earlier individual approvals do not change runtime context.

The builder starts with the previous full effective manifest, adds approved CREATE revisions, replaces approved UPDATE revisions and excludes approved REMOVE targets. Rejected proposals have no effect. Validation checks discriminated payload types, dependencies, entity references, semantic mapping source/table/columns and read-only SQL examples. Structural validation does not decide business truth.

- No semantic changes or all rejected: NO_CHANGE, no version allocation.
- Structural failure: BUILD_BLOCKED with persisted errors; previous ACTIVE stays active. Corrections require a new proposal.
- Successful build: monotonic integer v1, v2, ... with a full immutable snapshot.

One transaction materializes revisions, evidence links, relational graph entities/edges, exact revision membership, and the snapshot; supersedes the old version; activates the new version; and retires removed assets. A partial unique index enforces one ACTIVE version per package. All changes roll back on failure. Immutable-table triggers protect historical asset revisions, package manifests/snapshots and review history. REMOVE never deletes history or turns an approved historical asset into a rejected proposal.

There is exactly one package per Workspace for this MVP (`UNIQUE(workspace_uuid)` on `context_package`). No cross-Workspace query, multiple packages per Workspace, four-tier inheritance hierarchy or automatic expiry scheduler is implemented. A learning-to-SQL feedback loop is not implemented, but query feedback (upvote/downvote, optional comment, LLM critique on an uncommented downvote) is persisted to PostgreSQL+pgvector and retrieved per Workspace as few-shot answering guidance -- see `runtime/feedback.py`. Validity and conditions remain available for answer reasoning.
