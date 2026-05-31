---
name: maid-plan-review
description: "Review a MAID manifest and its behavioral tests before implementation. Verifies the plan is complete, scoped correctly, and the tests form a genuine behavioral contract. Use after maid-planner produces a manifest and before implementation starts. Triggers: review the manifest, review the plan, check the manifest, is this plan ready, maid plan review."
---

# MAID Plan Review

Review a manifest and its behavioral tests before implementation begins. This is the quality gate between planning and coding.

## Rules

- NEVER modify the manifest or tests during review.
- NEVER proceed to implementation if blockers are found.
- ALWAYS confirm the red phase.
- Judge the plan, not the idea.
- Treat missing explicit signatures, missing field types, and `E200` behavioral misses as blockers.
- Treat missing rationale for important design choices as a revision item.
- Treat generic, missing, or unpaired `temptations` as blockers when the task has obvious implementation shortcuts.

## Phase 1 — Locate the Manifest

Use the path provided by the user. If none is provided, inspect recent `manifests/*.manifest.yaml` files and pick the most likely draft. Ask only if the choice is ambiguous.

## Phase 2 — Structural Review

Check:

- schema version
- specific goal
- manifest type
- created date
- adequate description
- valid `files.create`, `files.edit`, `files.read`, and `validate` sections
- lean task-specific `temptations` when implementation gaming is plausible
- sensible paths and dependency coverage

## Phase 3 — Scope Review

Flag manifests that are too broad, too narrow, or missing critical read dependencies.

For MAID 2.7.2 manifests, distinguish contracted files from contextual files:

- `files.create` and `files.edit` are the public artifact contract.
- `files.read` may include files that are touched but not themselves contracted,
  such as behavioral specs or existing components where the task only replaces
  call sites to delegate into a new sprout.
- Do not require a touched file to move from `files.read` to `files.edit` unless
  the task intentionally changes or contracts that file's public artifacts, or
  implementation validation rejects the scope.
- Be wary of forcing large existing public classes into `files.edit`; MAID may
  then require declarations for the class's full public surface, expanding the
  manifest beyond the behavioral contract.

## Phase 4 — Artifact Quality Review

Confirm:

- public API only
- exact names
- methods/functions include `args` and `returns`
- zero-arg methods/functions use `args: []`
- attributes include `of` and `type`
- type aliases include explicit `type`
- every declared symbol is necessary and complete

## Phase 5 — Test Quality Review

Read the behavioral tests and check:

- behavioral purity
- no private-state or private-helper access unless the public contract explicitly exposes it
- happy path coverage
- edge-case coverage
- failure-mode coverage
- exact symbol references for every declared production artifact

## Phase 5.5 — Adversarial Review

Review the manifest and tests as if trying to make them pass with the lowest-quality implementation. Flag:

- risks named without a concrete `instead`
- broad assertions that allow hollow code
- schema or type looseness that can hide bad behavior
- tests coupled to internals rather than public behavior
- missing rationale that leaves the implementer guessing

Require revisions until the clean implementation path is explicit.

## Outcome-Aware MAID Guidance

Outcome records are deterministic manifest data, not agent-only memory. When
the project has Outcome support, `maid learn`, `maid recall`, and
`maid insights` provide explicit evidence that can inform review questions.

For plan review:

- Check whether the draft used relevant recalled Outcome evidence when the
  planner had a learned index or the user requested outcome-aware planning.
- Missing relevant Outcome recall is a review question, not automatic rejection;
  decide whether the omission weakens scope, tests, rationale, or temptations.
- Recalled outcomes are planning evidence only and do not replace behavioral tests, declared scope, validation, or review.

## Phase 6 — Behavioral Validation

Run:

```bash
maid validate manifests/<slug>.manifest.yaml --mode behavioral
```

Any `E200 Artifact '<name>' not used in any test file` result is a blocker.

## Phase 7 — Confirm Red Phase

Run the manifest validation commands before implementation. The tests must fail for the intended reason.

## Phase 8 — Verdict

End with one explicit verdict:

- `Approved`
- `Needs revision`
- `Rejected`

Keep findings concise and actionable.
