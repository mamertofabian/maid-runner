---
name: maid-planner
description: Plan a coding task as a machine-checkable MAID manifest instead of free-form markdown. Analyzes the project, asks clarifying questions, drafts a manifest with behavioral tests, validates it with `maid validate --mode behavioral`, and gets user approval. The manifest becomes the implementation contract. Use at the start of every new feature, bug fix, or refactor.
---

# MAID Planner

Replace free-form markdown planning with a machine-checkable MAID manifest contract. The plan IS the contract.

## Rules

- NEVER write implementation code before the manifest is approved.
- NEVER assume missing information. Ask instead.
- NEVER skip validation. The manifest MUST pass `maid validate --mode behavioral` before approval.
- NEVER go off-manifest. If new work is discovered during implementation, stop and create a new manifest.
- NEVER approve a manifest with generic artifact declarations. The manifest must declare exact public symbols, signatures, return types, and field types.
- ALWAYS include task-specific `temptations` when the work has likely shortcuts. Each entry must pair a concrete risk with the procedure to use instead.
- ALWAYS record rationale for important design decisions in the manifest description or artifact descriptions.

## Prerequisites

Before starting, verify:

```bash
which maid 2>/dev/null || pip show maid-runner 2>/dev/null
```

If `maid` is not available, tell the user:

```text
maid-runner is not installed. Install it with:
  pip install maid-runner
```

Do not proceed until `maid` is available.

## Phase 1 — Analyze the Project

Read the project silently. Check:

1. Directory structure (top 2 levels)
2. Package config (`pyproject.toml`, `package.json`, etc.)
3. Existing `manifests/` for patterns and active contracts
4. Existing tests and conventions
5. `README.md` or project documentation
6. Current MAID state via `maid validate`

## Phase 2 — Ask Clarifying Questions

- Ask at most 5 questions in one round.
- Ask only what is critical and cannot be inferred.
- Number the questions.

Wait for the user's response before proceeding.

## Phase 3 — Draft the Manifest

Create a draft manifest in `manifests/<slug>.manifest.yaml`.

### Temptations and Rationale

When the task has likely implementation shortcuts, add a top-level `temptations` section immediately after `description`.

Rules:

- Use 3-5 entries for substantial work; keep it shorter for narrow fixes.
- Every entry must have `risk` and `instead`.
- Make risks task-specific, concrete, and lint-like.
- Put generic rules in project guidance, not every manifest.
- Write the clean path as a procedure, not a vague warning.

Example:

```yaml
description: |
  Add public manifest support for task-specific implementation guidance.
temptations:
  - risk: "Do not loosen schema additionalProperties to make tests pass."
    instead: "Declare the exact top-level schema property and test valid/invalid cases."
  - risk: "Do not test private parser helpers directly."
    instead: "Exercise behavior through load_manifest, save_manifest, and validate_manifest_schema."
```

For important choices, include rationale: state what was chosen and why. The implementer should not have to infer architectural intent from green tests alone.

### Artifact Declaration Rules

- Public symbols only. Private `_` symbols do not belong in the contract.
- `files.create` is Strict Mode.
- `files.edit` is Permissive Mode.
- `kind` values: `class`, `function`, `method`, `attribute`, `interface`, `type`, `enum`, `namespace`, `test_function`
- `function` and `method` artifacts MUST include `args` and `returns`.
- Zero-argument functions and methods MUST use `args: []`.
- `attribute` artifacts MUST include `of` and `type`.
- `type` artifacts MUST include the exact alias target in `type`.
- Reject placeholders like `any`, `object`, `ClassName`, or prose-only declarations when precision is required.

## Phase 4 — Write Behavioral Tests

Write the behavioral tests referenced by the manifest `validate` commands.

Requirements:

- Tests must import and use every declared production artifact by exact identifier.
- Tests must define WHAT the code does, not HOW it is implemented.
- Tests must be deterministic and independent.
- Type artifacts must be referenced through type annotations, variables, callbacks, object shapes, or field access.

## Phase 5 — Confirm Red Phase

Run the behavioral tests against the current codebase before implementation.

The tests must fail. If they pass, the contract is weak or malformed.

## Phase 6 — Validate the Manifest

Run:

```bash
maid validate manifests/<slug>.manifest.yaml --mode behavioral
```

The manifest is not ready if behavioral validation reports any error, including `E200` unreferenced artifacts.

### Pre-Approval Checklist

- Every required public symbol is declared.
- Every function/method has `args` and `returns`.
- Every zero-arg function/method uses `args: []`.
- Every interface or type field is declared as an `attribute` with `of` and `type`.
- Every declared production artifact is referenced in behavioral tests by exact identifier.
- `maid validate --mode behavioral` passes with zero errors.
- The red phase fails for the intended reason.
- `temptations` are lean, task-specific, and each has a concrete `instead`.
- The manifest explains why important design choices were made.

### Adversarial Self-Review

Before presenting the plan, review your own manifest and tests as if trying to game them. Check for:

- private-state or private-helper access in tests
- over-broad assertions that allow hollow implementations
- schema loosening or catch-all types
- implementation-coupled tests that reward the wrong structure
- missing escape hatches for cases where the plan proves wrong

Revise the manifest, tests, or `temptations` until the clean path is explicit.

## Phase 7 — Review the Plan

Before presenting the manifest, run a read-only MAID plan review using the `maid-plan-review` skill when available. The reviewer must confirm:

- behavioral validation passes
- every declared artifact is exercised
- the red phase is genuine
- the scope is appropriate

Revise the manifest and tests if review finds blockers.

## Phase 8 — Present for Approval

Present the manifest draft, affected files, declared artifacts, and validation status. Stop for user approval before any implementation begins.
