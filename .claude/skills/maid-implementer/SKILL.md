---
name: maid-implementer
description: Implement code against an approved MAID manifest. Loads only the declared files, writes code to pass behavioral tests, validates with `maid validate --mode implementation`, and iterates until all checks pass. Use after a manifest is approved by maid-planner (or manually).
---

# MAID Implementer

Execute code implementation against an approved MAID manifest. The manifest is the contract.

## Rules

- Load the manifest first.
- Implement only what the manifest declares.
- `files.create` is Strict Mode. `files.edit` is Permissive Mode.
- Implementer sessions run validation gates with `--packet`; for example,
  `maid validate --packet` and `maid verify --packet`.
- Run `maid validate --mode implementation` after implementation.
- Run all manifest `validate` commands.
- NEVER modify code not listed in the manifest `files.create` or `files.edit`.
- NEVER modify the manifest during implementation.
- NEVER modify behavioral tests unless the user explicitly approves changing the contract.
- If implementation validation exposes a bad manifest, write `plan-revision.md` explaining the issue and stop. Do not force tests green by working around a bad plan.
- If the manifest has `temptations`, restate the relevant risk/procedure pairs before editing and treat each `instead` as the working procedure.

## Packet-Driven Retry Gates

When a packet-aware gate fails, read `.maid/last-failure-packet.json` instead of re-exploring the repository. The packet is the retry context: failed command argv, exit code, project root, failed manifest excerpts, diagnostics, `next_action` repair recipes, failed-command output tails, and environment versions.

Respect `next_action` exactly. Valid kinds include `edit-implementation`,
`edit-tests`, `edit-manifest`, `run-command`, `revise-plan`, and
`escalate-human`; kinds that change tests or manifests route through explicit
plan revision when the contract must change. Recipes never authorize weakening tests or manifests to silence errors, and they never authorize weakening tests or manifests as the first remedy for an implementation failure.

Stop at the default 5 attempt bound. If the gate still fails, or the packet
requests `escalate-human`, stop and escalate to a human with the final packet
instead of looping, hiding the failure, or broadening scope.

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

## Phase 1 — Load the Manifest

Read the approved manifest and extract:

- files to create
- files to edit
- read-only dependencies
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

- Consult recalled Outcome records when choosing focused tests and code patterns.
- Do not broaden the approved manifest scope because an older Outcome mentioned adjacent work.
- Treat `maid insights` as aggregate evidence for recurring lessons, not as
  permission to skip the current manifest contract.
- Recalled outcomes are planning evidence only and do not replace behavioral tests, declared scope, validation, or review.

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

- add the declared artifacts conservatively
- preserve existing behavior unless the tests require change

### Active Task Scope Guidance

When implementing a promoted draft, run
`maid task start manifests/<slug>.manifest.yaml` after promotion and before
implementation edits so hook integrations can evaluate writes against the
active manifest. At handoff, after implementation review and Outcome capture,
run `maid task stop` to clear the pointer.

Interactive editor sessions use the default fail-open policy: no active task
and internal hook errors allow the edit. Locked-down autonomous loops should
pass `--strict` to deny those outcomes. The hook is advisory edit-time
infrastructure only. maid verify changed-scope checks remain the authoritative handoff evidence.
Hook decisions do not replace validation or add `ErrorCode` entries.

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

Use a fresh read-only reviewer with an explicit review packet containing the
manifest path, changed files, diff summary, and validation output. Do not rely
on the full implementation transcript, and do not require separate per-turn
reviewer-agent approval when repo guidance grants standing authorization.

Treat the review verdict as a gate. Fix concrete implementation defects, rerun
focused validation, and run another implementation review. Repeat until the
latest review verdict is `Ready to merge`, or stop with `Needs changes` or
`Needs discussion` if the remaining issue requires user or plan revision input.

## Phase 8 — Report

Report changed files, validation results, reviewer verdict, and whether a
subagent reviewer was used. Only call the work ready for commit or further
integration when validation passes and the latest review verdict is ready.
