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
- Run `maid validate --mode implementation` after implementation.
- Run all manifest `validate` commands.
- NEVER modify code not listed in the manifest `files.create` or `files.edit`.
- NEVER modify the manifest during implementation.
- NEVER modify behavioral tests unless the user explicitly approves changing the contract.
- If implementation validation exposes a bad manifest, write `plan-revision.md` explaining the issue and stop. Do not force tests green by working around a bad plan.
- If the manifest has `temptations`, restate the relevant risk/procedure pairs before editing and treat each `instead` as the working procedure.

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

Fix concrete implementation defects and revalidate before finishing.

## Phase 8 — Report

Report changed files and validation results. If all checks pass, the work is ready for commit or further integration.
