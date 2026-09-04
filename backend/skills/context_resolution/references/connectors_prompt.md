ROLE
You are building production orchestrator code for the CCE Connectors stage ONLY —
source-registry, credential-resolution, strucutred_source_connect,
document-source-connect. Scope stops the instant a connection handle is
returned READY. Nothing past that is in scope.

STEP 0 — DISCOVER SCOPE, DO NOT ASSUME IT
1. Locate exactly these four skills under skills/Connect_Ingest_Ground/. If
   any is missing, or you find extras you weren't told about, stop and ask —
   do not substitute or improvise.
2. Never open, read, or import anything under skills/Dontreadthis/.
3. Read each SKILL.md in full — numbered core rules, contract table,
   checklist — plus its test-suite.json and test-data/*.json. The rules are
   the spec; quote exact rule IDs as you implement against them, don't
   paraphrase from memory.
4. Produce a manifest (skills found, one line each on what they validate,
   exact call order) and wait for my go-ahead before designing anything.

═══════════════════════════════════════════════════════════════════
ENGINEERING GUARDRAILS — apply to every line of code, no exceptions
═══════════════════════════════════════════════════════════════════

1. KEEP AGENTS NARROW AND MODULAR
   - This stage requires ZERO LLM inference. Registry validation, credential
     resolution, and connect probing are deterministic — do not introduce an
     LLM call anywhere in this stage "to be safe" or "to handle edge cases."
     If you believe judgment is needed somewhere, stop and name exactly where
     and why — don't quietly add a model call.
   - Each of the four skills is wrapped as one narrow function with one input
     shape and one output shape. A function for source-registry never also
     resolves credentials; a function for structured-connect never also
     validates the registry entry. No shared mutable logic between them —
     if two skills need the same helper, it lives in a common utility, not
     borrowed from one skill's module into another's.
   - The orchestrator itself does no validation logic of its own — it only
     sequences calls to the four narrow functions and inspects their
     returned status. If you catch yourself writing an if/else that
     re-implements a rule already inside a skill's own validator, delete it
     and call the validator instead.

2. STATE BELONGS IN SOFTWARE, NOT THE MODEL
   - All pipeline state — which source is being processed, its current
     stage, its descriptor, its lease, its READY/REJECTED status — lives in
     an explicit state object/store you define in code (e.g. a typed dict,
     dataclass, or row in a state table), never in an LLM's context window,
     never inferred by asking a model "what happened last."
   - This state store must be inspectable independent of any conversation —
     given a source_id, I should be able to query current stage and status
     directly from the store, not by re-running or re-asking anything.
   - Nothing about which stage a source is in, or whether it passed, is ever
     "remembered" implicitly. It's a field, with a value, written by code.

3. OWN THE LOOP AND ENFORCE HARD STOPS
   - The orchestrator (deterministic code) owns the control loop — it decides
     what runs next, never an autonomous agent looping on its own judgment.
   - No retries. A REJECTED status from any skill is terminal for that
     source in this run — do not retry with modified input, don't loop back
     with "let me try again," don't add exponential backoff around a
     validation rejection (backoff belongs around transient network calls
     to the real adapter, never around a contract violation).
   - Hard stop after Connectors stage, enforced in code — not a prompt-level
     instruction to "wait for approval" but an actual halt (process exit,
     explicit pending-approval state written to the state store) after every
     source reaches READY or REJECTED. The next stage cannot start unless an
     explicit approval flag is set externally.
   - Cap everything bounded: connection timeout, write-probe timeout, max
     sources per run. No unbounded loops anywhere in this stage.

4. LOG EVERYTHING CONTINUOUSLY
   - Every skill call emits one structured log line minimum: timestamp,
     source_id, adapter, kind, skill name, input shape (no secrets), output
     status, violated_rule (if any). Log the rejection with the same rigor
     as the success — a REJECTED result is not a failure to hide, it's the
     correct output to record.
   - Never log a resolved secret, lease's underlying credential value, or
     raw request/response containing one — log the lease_id and backend
     only, exactly as credential-resolution's own contract requires (CRD03).
   - Logs are append-only and structured (JSON lines or equivalent) — not
     print statements meant for a human to eyeball once, but a durable trail
     meant to be queried later.

5. IMPLEMENT REQUEST TRACING
   - Generate one trace_id/correlation_id per orchestration run, before the
     first skill call. Propagate it through every function call, every log
     line, and every state store write for that run.
   - Every one of the four skill calls for a given source must be
     reconstructable end-to-end from trace_id alone: given a trace_id, I
     should be able to pull the full sequence — registry check → credential
     resolution → connect attempt — in order, with each one's status.
   - This is infrastructure-level tracing, distinct from (and a precursor
     to) the provenance-capture skill used later in Ingest & Ground —
     tracing covers this run's execution path, including rejections;
     provenance covers content lineage. Don't conflate the two or skip
     tracing because "provenance will cover it later."

═══════════════════════════════════════════════════════════════════

AGNOSTICISM CONSTRAINT
- The only branch point anywhere in this code is on `kind` (structured vs
  unstructured), resolved from the registry descriptor. Never branch on
  adapter/vendor name. Snowflake and a PDF source are two instances of the
  same two lanes — adding Postgres or SharePoint later must require zero
  changes to orchestrator code, only a new registry entry + adapter
  implementation behind the existing interface.

CREDENTIAL CONSTRAINT
- No inline credential ever, anywhere, in any log, state field, or profile.
  Only `credential_ref` flows in; only credential-resolution resolves it;
  the resulting lease (lease_id, backend, role, grants, ttl_seconds) is the
  only credential-shaped object that may exist past that point.

DELIVERABLES, IN ORDER — STOP AFTER EACH, WAIT FOR "APPROVE"
1. Manifest (Step 0).
2. Design note: state store schema, trace/log format, the fork point, the
   two lane sequences, and where each of the five guardrails above shows up
   concretely in the design.
3. Orchestrator + adapter code, once approved.
4. Regression run against each skill's own test-suite.json.
5. Real fixture run: an actual Snowflake source (structured lane) and an
   actual PDF source (unstructured lane), both ending at READY with full
   trace and log output shown, not described.

If any skill's rule requires an input this stage can't produce, stop and
name the exact gap rather than inventing a workaround.
