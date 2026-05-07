---
name: maid-implementation-review
description: Review an implementation produced from an approved MAID manifest. Confirms changed files stay within manifest scope, declared artifacts exist, validations pass, and the behavior matches the contract. Use after maid-implementer or after any MAID-backed code change before merge.
---

# MAID Implementation Review

Review MAID-backed implementation work in read-only mode. Confirm the code matches the approved contract and that validation integrity was preserved.

## Rules

- NEVER edit files.
- NEVER modify tests or manifests during review.
- Confirm changed implementation stays within the manifest `files.create` and `files.edit` scope.
- Flag any implementation-phase manifest or behavioral-test edit as a process violation unless explicitly approved by the user.
- Treat concrete behavior regressions, undeclared public API drift, and missing validation as primary findings.
- Audit fidelity to the approved plan, including rationale and `temptations`; passing tests are not sufficient if the implementation took a path the manifest warned against.
- If `plan-revision.md` exists, review it as a stop signal rather than an implementation failure.

## Phase 1 — Identify the Active Manifest

Use the manifest path provided by the user. If none is provided, inspect recent manifests and current changed files to infer the most likely approved contract.

## Phase 2 — Review Scope

Compare the working tree or branch state against the manifest:

- only allowed implementation files were changed
- read-only dependency files were not edited without approval
- no undeclared public symbols leaked into strict files

## Phase 3 — Review Declared Artifacts

Confirm declared artifacts exist with the expected names and parent relationships. Treat implementation-validation misses as blockers.

## Phase 4 — Review Plan Fidelity

Compare implementation choices against the approved manifest:

- declared rationale was followed or explicitly justified
- `temptations` risks were not taken
- each relevant `instead` procedure was followed
- no private-state access, private-helper imports, schema loosening, or test-coupled shortcuts were introduced
- no undeclared public API was added to make tests pass

Treat a direct violation of a manifest temptation as a finding even when validation passes.

## Phase 5 — Review Behavioral Coverage

Check that the behavioral tests still exercise the approved contract and that implementation changes did not weaken validation.

## Phase 6 — Run Practical Validation

Where practical, run:

```bash
maid validate manifests/<slug>.manifest.yaml --mode implementation
maid test --manifest manifests/<slug>.manifest.yaml
```

If the environment or project shape makes a command impractical, say so explicitly.

## Phase 7 — Report

Prioritize:

1. blockers
2. should-fix items
3. nitpicks

End with one explicit verdict:

- `Ready to merge`
- `Needs changes`
- `Needs discussion`
