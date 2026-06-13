---
name: maid-planner
description: Plan a coding task as a machine-checkable MAID manifest instead of free-form markdown. Analyzes the project, asks clarifying questions, drafts or refines a manifest, and for implementation-ready plans adds behavioral tests, validates with `maid validate --mode behavioral`, and gets user approval. The promoted manifest becomes the implementation contract. Use at the start of every new feature, bug fix, or refactor.
---

# MAID Planner

Replace free-form markdown planning with a machine-checkable MAID manifest contract. The plan IS the contract.

## Rules

- NEVER write implementation code before the manifest is approved.
- NEVER assume missing information. Ask instead.
- NEVER skip validation for an implementation-ready contract. The manifest MUST
  pass `maid validate --mode behavioral` before approval, promotion, or
  immediate implementation. Early draft inventory may be schema-only or mention
  planned tests, but must be labeled and reported as not promotion-ready yet.
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

## Outcome-Aware MAID Guidance

Outcome records are deterministic manifest data, not agent-only memory. When
the project has Outcome support, use `maid learn`, `maid recall`, and
`maid insights` as explicit evidence sources and cite the manifest Outcome docs
instead of relying on private memory.

For planning:

- Run `maid learn` before `maid recall` when the Outcome index is stale.
- If the Outcome index is missing, run `maid learn` once. If no index is
  created because no completed Outcome records exist, state that no advisory
  history is available and skip recall.
- `maid recall --for-manifest <draft>` is allowed only as a query builder for
  related completed Outcome records; do not expect an unimplemented draft to
  have its own Outcome record.
- Review recalled Outcome lessons before drafting a new manifest when recall
  results are available.
- Use `maid insights` only as aggregate evidence for recurring lessons, not as
  generated narrative authority.
- Recalled outcomes are planning evidence only and do not replace behavioral tests, declared scope, validation, or review.

### Manifest-Derived Outcome Recall

Before drafting an implementation-ready manifest, consult related completed
Outcome records when a learned Outcome index is available:

```bash
maid recall --for-manifest <path>
maid recall --for-manifest <path> --plan-packet
```

If the index is stale, the stale index fails by default. The remedy is to run
`maid learn`, or pass `--allow-stale-index` only when a stale advisory read is
acceptable. If `.maid/outcomes.json` is missing, run `maid learn` once; if no
completed Outcome records exist, report that no advisory history is available
and skip recall. The manifest path may be an unimplemented draft, but recall is
only a query for related completed Outcome records, not a lookup for the
draft's own Outcome.

Recalled Outcomes are planning evidence only. They do not replace the new
manifest's behavioral tests, declared artifacts, validation commands, or
implementation review.

## Phase 2 — Ask Clarifying Questions

- Ask at most 5 questions in one round.
- Ask only what is critical and cannot be inferred.
- Number the questions.

Wait for the user's response before proceeding.

## Phase 3 — Draft the Manifest

Create a draft manifest using the repository's draft convention. In this repo,
planning inventory belongs in `manifests/drafts/<slug>.manifest.yaml`; promote
one implementation-sized child to `manifests/<slug>.manifest.yaml` only after
the promotion criteria are satisfied.

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
- `files.create` and `files.edit` declare the public artifact contract for new
  or intentionally changed public API.
- `files.read` lists dependency context and may include touched-but-uncontracted
  files when the task only rewires call sites, adds/updates validation tests, or
  otherwise does not contract that file's public surface. Do not treat
  `files.read` as automatically read-only; verify the pinned MAID runner's
  implementation validation and the manifest intent.
- Avoid moving a large existing file into `files.edit` just because a narrow
  delegation edit is required. In MAID 2.7.2, declaring an existing public class
  can require its full remaining public surface to be declared. Use `files.edit`
  when the manifest intentionally contracts public artifacts in that file.
- `kind` values: `class`, `function`, `method`, `attribute`, `interface`, `type`, `enum`, `namespace`, `test_function`
- `function` and `method` artifacts MUST include `args` and `returns`.
- Zero-argument functions and methods MUST use `args: []`.
- `attribute` artifacts MUST include `of` and `type`.
- `type` artifacts MUST include the exact alias target in `type`.
- Reject placeholders like `any`, `object`, `ClassName`, or prose-only declarations when precision is required.

## Phase 4 — Write Behavioral Tests

For an implementation-ready plan, write the behavioral tests referenced by the
manifest `validate` commands. For early draft inventory, it is acceptable to
describe planned tests and validation commands before the files exist, but the
draft is not approval-ready or promotable until the tests are created.

Requirements:

- Tests must import and use every declared production artifact by exact identifier.
- Tests must define WHAT the code does, not HOW it is implemented.
- Tests must be deterministic and independent.
- Type artifacts must be referenced through type annotations, variables, callbacks, object shapes, or field access.

## Phase 5 — Confirm Red Phase

Run the behavioral tests against the current codebase before implementation.

The tests must fail. If they pass, the contract is weak or malformed. If the
test files are still planned and absent, red phase is not confirmed yet; do not
present the draft as approved, promotable, or ready for implementation.

## Phase 6 — Validate the Manifest

Run:

```bash
maid validate manifests/<slug>.manifest.yaml --mode behavioral
```

The manifest is not ready for approval, promotion, or immediate implementation
if behavioral validation reports any error, including `E200` unreferenced
artifacts. For draft inventory, record the result as pending test creation
rather than treating the draft's existence as invalid.

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

Present the manifest draft, affected files, declared artifacts, validation
status, and red-phase result. Stop for user approval before any implementation
begins.

After the user approves the plan, end the planning loop by running:

```bash
maid plan lock manifests/<slug>.manifest.yaml
```

Use the approved manifest path. Do not hand off implementation until the plan
lock exists, unless the user explicitly chooses a no-run lock with
`maid plan lock --no-run` and accepts `red_evidence: null`.
