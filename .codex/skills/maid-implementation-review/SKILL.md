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
  subagent before the final verdict whenever subagents are available and not
  explicitly disabled for the turn.
- Reviewer subagents must be fresh, context-minimal review agents. Never use a
  full-history fork or pass prior implementation reasoning, conclusions, or chat
  transcript unless the review explicitly depends on a user quote.
- If your prompt identifies you as the reviewer subagent, do not spawn another
  subagent. Perform the review locally and return the verdict.
- Confirm changed files stay within the manifest scope: `files.create` and
  `files.edit` for contracted public artifacts, plus `files.read` for declared
  dependency/context files whose public surface is not being contracted.
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
the environment supports subagents and they have not been explicitly disabled
for the turn:

- prefer `agent_type=explorer`
- use a fresh agent with `fork_context=false`; never set `fork_context=true` for
  an independent reviewer
- leave the model unset unless the user or local project instructions require a
  specific model
- pass the review packet explicitly
- instruct the subagent not to edit files and not to spawn further subagents
- wait for the subagent verdict before final handoff
- close the subagent thread after consuming the verdict

Do not skip the subagent because the current turn did not separately mention
subagent authorization when the target repo, active skill, or user prompt grants
standing authorization for MAID reviewer subagents. Fall back to local-only
review only when the subagent tool is technically unavailable or the user
explicitly disables subagents for that turn.

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

- only files declared in `files.create`, `files.edit`, or `files.read` were
  changed
- `files.read` changes are limited to the manifest intent, such as behavioral
  tests, imports, or narrow call-site delegation through contracted artifacts
- no undeclared public symbols leaked into strict files
- do not flag a `files.read` edit solely because it was edited; first run or
  inspect pinned MAID implementation validation and determine whether the edit
  contracts public API that should be in `files.edit`

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

## Outcome-Aware MAID Guidance

Outcome records are deterministic manifest data, not agent-only memory. Use
`maid learn`, `maid recall`, and `maid insights` as deterministic context, but
keep implementation review focused on the current manifest, tests, validation,
and changed files.

For implementation review:

- After the review verdict is ready, check whether the completed manifest needs an `outcome:` record.
- Outcome capture happens after implementation review and before final handoff.
- Confirm new Outcome lessons cite concrete validation, review, or file evidence.
- Do not mark work ready if Outcome claims are not backed by validation and review evidence.
- Outcome records do not replace behavioral tests, declared scope, validation, or review.

### Manifest Outcome Record Check

After the review verdict is ready, check related completed Outcome records to
decide whether this completed manifest needs a new or updated Outcome record:

```bash
maid recall --for-manifest <path>
maid recall --for-manifest <path> --plan-packet
```

If the index is stale, the stale index fails by default. The remedy is to run
`maid learn`, or pass `--allow-stale-index` only when a stale advisory read is
acceptable. If `.maid/outcomes.json` is missing, run `maid learn` once; if no
completed Outcome records exist, report that no advisory history is available
and skip recall.

Use related completed Outcome records to avoid duplicate or unsupported
lessons. Outcome claims still need concrete validation and review evidence.
Recalled Outcomes are planning evidence only. They do not replace behavioral
tests, declared artifacts, validation commands, or implementation review.

## Phase 8 — Run Practical Validation

Where practical, run:

```bash
maid verify --require-plan-lock --require-red-evidence
maid validate manifests/<slug>.manifest.yaml --mode implementation
maid test --manifest manifests/<slug>.manifest.yaml
```

For high-risk changes where runtime evidence matters, also run
`maid verify --artifact-coverage --knockout`. Treat it as an opt-in
Python-only review gate that checks declared artifacts are executed by tests
and that breaking each declared function or method makes validation fail.

The `maid verify --require-plan-lock --require-red-evidence` command is the
implementation handoff gate for the approved plan lock and captured red-phase
evidence. Treat E700-E706 plan-lock failures as blockers unless the review
packet explicitly states that opt-in enforcement is out of scope for the task.
E700/E704/E705 requirement errors apply to manifests changed in the task window;
E701/E702/E703/E706 integrity errors are blockers regardless of task window
scope.

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

Include the reviewer subagent result when one was run: subagent id or nickname,
verdict, and whether it found blockers.

End with one explicit verdict:

- `Ready to merge`
- `Needs changes`
- `Needs discussion`
