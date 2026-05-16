---
name: maid-implementation-review
description: Review an implementation produced from an approved MAID manifest. Confirms changed files stay within manifest scope, declared artifacts exist, validations pass, and the behavior matches the contract. Use after maid-implementer or after any MAID-backed code change before merge.
---

# MAID Implementation Review

Review MAID-backed implementation work in read-only mode. Confirm the code matches the approved contract and that validation integrity was preserved.

## Rules

- NEVER edit files.
- NEVER modify tests or manifests during review.
- When you are the coordinating reviewer, run an independent read-only reviewer
  subagent before the final verdict whenever the Agent tool is available.
- Reviewer subagents must be fresh, context-minimal review agents. Never pass
  prior implementation reasoning, conclusions, or chat transcript unless the
  review explicitly depends on a user quote.
- If your prompt identifies you as the reviewer subagent, do not spawn another
  subagent. Perform the review locally and return the verdict.
- Confirm changed implementation stays within the manifest `files.create` and `files.edit` scope.
- Flag any implementation-phase manifest or behavioral-test edit as a process violation unless explicitly approved by the user.
- Treat concrete behavior regressions, undeclared public API drift, and missing validation as primary findings.
- Audit fidelity to the approved plan, including rationale and `temptations`; passing tests are not sufficient if the implementation took a path the manifest warned against.
- If `plan-revision.md` exists, review it as a stop signal rather than an implementation failure.

## Phase 1 — Identify the Active Manifest

Use the manifest path provided by the user. If none is provided, inspect recent manifests and current changed files to infer the most likely approved contract.

## Phase 2 — Build the Review Packet

Collect the context needed for an independent review:

- active manifest path and whether it was provided or inferred
- changed files from the working tree or compared branch
- relevant diff summary, especially public symbols, tests, and manifest edits
- validation commands already run and their results
- known environment limits that prevented validation
- any `plan-revision.md` stop signal

Do not pass the full implementation transcript to the subagent. Keep the review
independent by passing only the explicit packet above.

## Phase 3 — Run the Reviewer Subagent

Before reporting the final verdict, spawn one read-only reviewer subagent when
the Agent tool is available:

- use `subagent_type: "maid-implementation-reviewer"`
- pass the review packet explicitly
- instruct the subagent not to edit files and not to spawn further subagents
- wait for the subagent verdict before final handoff

If subagents are unavailable, perform the same review locally and state clearly
that no independent reviewer subagent was run.

Use this prompt shape:

```text
Read-only MAID implementation review requested. Do not edit files. You are the
independent reviewer subagent; do not spawn additional subagents.

Review the current implementation as if running `/review` on the changed files,
with extra attention to the approved MAID manifest:
<manifest path>

Review packet:
- changed files: <files>
- validation results: <commands and outcomes>
- known environment limits: <limits or none>
- plan revision signal: <path or none>

Prioritize findings over summaries. Look for correctness bugs, security or
authorization gaps, privacy leaks, persistence bugs, concurrency/idempotency
failures, runtime incompatibilities, stale manifest references, weak or missing
behavioral tests, and implementation drift from the manifest contract.

Do not treat passing tests or MAID validation as proof of correctness. Inspect
the changed files, relevant call sites, nearby helpers, schema constraints, and
the manifest's declared behavior. Consider how each new public helper or API
will be called from realistic routes, handlers, CLIs, services, or tests.

Return only actionable review output:
- findings first, ordered by severity
- severity labels such as P0/P1/P2
- file and line references
- brief impact explanation
- missing tests when they allow a bug to pass

If there are no findings, say that clearly and mention any residual test gaps or
risk. End with one verdict: ready, needs changes, or needs discussion.
```

## Phase 4 — Review Scope

Compare the working tree or branch state against the manifest:

- only allowed implementation files were changed
- read-only dependency files were not edited without approval
- no undeclared public symbols leaked into strict files

## Phase 5 — Review Declared Artifacts

Confirm declared artifacts exist with the expected names and parent relationships. Treat implementation-validation misses as blockers.

## Phase 6 — Review Plan Fidelity

Compare implementation choices against the approved manifest:

- declared rationale was followed or explicitly justified
- `temptations` risks were not taken
- each relevant `instead` procedure was followed
- no private-state access, private-helper imports, schema loosening, or test-coupled shortcuts were introduced
- no undeclared public API was added to make tests pass

Treat a direct violation of a manifest temptation as a finding even when validation passes.

## Phase 7 — Review Behavioral Coverage

Check that the behavioral tests still exercise the approved contract and that implementation changes did not weaken validation.

## Phase 8 — Run Practical Validation

Where practical, run:

```bash
maid validate manifests/<slug>.manifest.yaml --mode implementation
maid test --manifest manifests/<slug>.manifest.yaml
```

If the environment or project shape makes a command impractical, say so explicitly.

## Phase 9 — Reconcile and Report

If the reviewer subagent reports findings, decide whether each finding is valid
against the manifest and code. Do not edit files during review. Report valid
findings first; put invalid or out-of-scope reviewer notes in a brief residual
risk or dismissed-notes section only if useful.

Prioritize:

1. blockers
2. should-fix items
3. nitpicks

Include the reviewer subagent result when one was run: verdict and whether it
found blockers.

End with one explicit verdict:

- `Ready to merge`
- `Needs changes`
- `Needs discussion`
