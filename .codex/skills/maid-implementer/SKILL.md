---
name: maid-implementer
description: Implement code against an approved MAID manifest. Loads only the declared files, writes code to pass behavioral tests, validates with `maid validate --mode implementation`, and iterates until all checks pass. Use after a manifest is approved by maid-planner (or manually).
---

# MAID Implementer

Execute code implementation against an approved MAID manifest. The manifest is the contract.

## Rules

- Load the manifest first.
- Implement only what the manifest declares.
- `files.create` and `files.edit` declare contracted public artifacts.
- `files.read` may include touched-but-uncontracted files for behavioral tests,
  imports, or narrow call-site delegation when the manifest intent and pinned
  MAID implementation validation allow it.
- Run `maid validate --mode implementation` after implementation.
- Run all manifest `validate` commands.
- NEVER modify files not listed in the manifest `files.create`, `files.edit`, or
  `files.read`.
- NEVER modify the manifest during implementation.
- NEVER modify behavioral tests unless the user explicitly approves changing the contract.
- If implementation validation exposes a bad manifest, write `plan-revision.md` explaining the issue and stop. Do not force tests green by working around a bad plan.
- If the manifest has `temptations`, restate the relevant risk/procedure pairs before editing and treat each `instead` as the working procedure.

## Phase 1 — Load the Manifest

Read the approved manifest and extract:

- files to create
- files to edit
- read dependencies and any touched-but-uncontracted contextual files
- exact artifacts
- temptations and their `instead` procedures
- validation commands

If the manifest includes `temptations`, identify which entries apply to this implementation. Restate them briefly before coding so the sharp test-passing signal does not override the architectural guidance.

## Phase 2 — Load Dependencies

Read every file listed in `files.read` and the behavioral tests referenced by the manifest.

### Promoted Draft Recall

When implementation starts from a draft manifest, refresh recall before
promotion when completed Outcome records exist:

```bash
uv run maid learn
uv run maid recall --for-manifest manifests/drafts/<slug>.manifest.yaml --plan-packet
```

If `maid learn` finds no completed Outcome records, state that no advisory
history is available and continue. Use recalled lessons to sharpen test focus
and implementation risks. Recall is advisory planning context only; it does
not expand scope or replace red evidence, behavioral validation, plan lock,
implementation validation, or review.

## Outcome-Aware MAID Guidance

Outcome records are deterministic manifest data, not agent-only memory. When
the project has Outcome support, use `maid learn`, `maid recall`, and
`maid insights` as historical evidence only.

For implementation:

- Active insights trigger: review recurring Outcome lessons with `maid insights`
  before implementing the approved manifest. Treat insights as advisory
  aggregate evidence for recurring lessons, not as generated narrative authority.
- Consult recalled Outcome records when choosing focused tests and code patterns.
- Do not broaden the approved manifest scope because an older Outcome mentioned adjacent work.
- Treat `maid insights` as aggregate evidence for recurring lessons, not as
  permission to skip the current manifest contract.
- Use active recall guidance to thread the planner's recalled evidence into
  implementation decisions while staying inside the approved scope.
- To intentionally include instructive failed or abandoned Outcome lessons,
  refresh the index with this opt-in command, then recall from that index:

```bash
maid learn --include-status completed --include-status abandoned
```

  This is an intentional opt-in for failure lessons; the completed-only default
  is unchanged.
- Recalled, aggregated, and digested Outcomes are planning evidence only. They
  do not replace behavioral tests, declared scope, validation, approval, done
  gates, or review, and they do not create an approval, promotion, done, or
  review gate.

### Manifest-Derived Outcome Recall

When choosing focused tests and code patterns, consult related completed
Outcome records for the approved manifest when a learned Outcome index is
available:

```bash
maid recall --for-manifest <path>
maid recall --for-manifest <path> --plan-packet
```

If the index is stale, the stale index fails by default. The remedy is to run
`maid learn`, or pass `--allow-stale-index` only when a stale advisory read is
acceptable. If `.maid/outcomes.json` is missing, run `maid learn` once; if no
completed Outcome records exist, report that no advisory history is available
and skip recall.

Use recall to identify relevant prior lessons, but stay inside the approved
manifest scope. Recalled Outcomes are planning evidence only. They do not
replace behavioral tests, declared artifacts, validation commands, or
implementation review.

### Learning Evidence Digestion

The learning evidence digestion step is advisory evidence handling.

Close the loop between completed Outcome records and current agent decisions;
do not dump a raw recall or insights transcript into the implementation notes.
Identify applicable lessons, reject stale or irrelevant lessons with a reason,
and state what changed because of the evidence. For implementation, name the
effect on focused tests, implementation approach, or risk controls inside the
approved scope. The learning evidence digestion step is advisory evidence
handling, not a separate gate.

## Plan Revision Recovery

If implementation review requires review-driven behavioral contract changes
after implementation already exists, do not invent a manual stash or worktree
procedure. Use the sanctioned recovery command:

```bash
maid plan revise <manifest> --reason "<text>" --stash-implementation
```

Use `--stash-implementation` only for review-driven behavioral contract changes
that need fresh red evidence while declared implementation changes are
temporarily hidden. For metadata-only cleanup on a locked manifest, use
`maid plan revise <manifest> --reason "<text>" --preserve-red-evidence`
instead.

## Phase 3 — Implement

If the plan appears wrong, incomplete, or impossible, stop and write `plan-revision.md` instead of editing around it. Include:

- the manifest path
- the contradiction or missing context
- the file/test evidence
- the proposed manifest or test revision

For `files.create`:

- define exactly the declared public artifacts
- keep additional helpers private
- avoid undeclared public symbols

For `files.edit`:

- add or change the declared artifacts conservatively
- preserve existing behavior unless the tests require change

For `files.read`:

- treat the file as contextual unless the manifest description clearly allows a
  narrow edit
- allowed narrow edits include behavioral spec coverage, imports, and call-site
  replacement that delegates to contracted artifacts
- do not introduce or change public API from a `files.read` file; stop for a
  plan revision if that becomes necessary

## Phase 4 — Validate Implementation

Run:

```bash
maid validate manifests/<slug>.manifest.yaml --mode implementation
```

Fix structural mismatches in code only. If the manifest itself is wrong, write `plan-revision.md` and stop.

## Phase 5 — Run Behavioral Tests

Run all `validate` commands from the manifest.

- Fix behavior in code, not in tests.
- If a test appears wrong, write `plan-revision.md` and stop.

## Phase 6 — Run Full Validation

Run:

```bash
maid validate
maid test
```

This ensures the implementation does not break other MAID contracts.

## Phase 7 — Review the Implementation

Before reporting completion, run a read-only MAID implementation review using the `maid-implementation-review` skill when available. The reviewer should confirm:

- changed files stayed within manifest scope
- declared artifacts exist
- validation passed
- no implementation-phase drift or process violations were introduced

When that review uses a subagent, spawn a fresh reviewer with an explicit review
packet. Do not fork the full session context into the reviewer; this preserves
the same independent-review pattern used by loop-style reviewer agents.
Do not require a separate per-turn subagent approval when the target repo,
active skill, or user prompt grants standing authorization for MAID reviewer
subagents.

Treat the review verdict as a gate. Fix concrete implementation defects, rerun
focused validation, and run another implementation review. Repeat until the
latest review verdict is `Ready to merge`, or stop with `Needs changes` or
`Needs discussion` if the remaining issue requires user or plan revision input.

## Phase 8 — Report

Report changed files, validation results, reviewer verdict, and whether a
subagent reviewer was used. Only call the work ready for commit or further
integration when validation passes and the latest review verdict is ready.
