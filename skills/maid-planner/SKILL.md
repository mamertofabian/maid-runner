---
name: maid-planner
description: Plan a coding task as a machine-checkable MAID manifest instead of free-form markdown. Analyzes the project, asks clarifying questions, drafts a manifest with behavioral tests, validates it, and gets user approval. The manifest becomes the implementation contract. Use at the start of every new feature, bug fix, or refactor.
---

# MAID Planner Skill

## Rules

- NEVER write implementation code before the manifest is approved.
- NEVER assume missing information. Ask instead.
- NEVER skip validation. The manifest MUST pass `maid validate --mode behavioral` before approval.
- NEVER go off-manifest. If new work is discovered during implementation, stop and create a new manifest.
- ALWAYS treat the manifest as the primary contract. Tests support it; they do not replace it.

---

## Prerequisites

Before starting, verify the environment:

```bash
which maid 2>/dev/null || pip show maid-runner 2>/dev/null
```

If `maid` is not available, tell the user:

```
maid-runner is not installed. Install it with:
  pip install maid-runner
  # or: uv pip install maid-runner
```

Do not proceed until `maid` is available.

---

## Phase 1 — Analyze the Project

Read the project silently before asking anything. Check:

1. Directory structure (top 2 levels)
2. Package config (`pyproject.toml`, `package.json`, etc.)
3. Existing `manifests/` directory — read recent manifests to understand patterns and active contracts
4. Existing `tests/` directory structure and conventions
5. `README.md` or project documentation
6. Run `maid validate` to see current validation state (what passes, what's pending)

Do not output analysis results unless directly relevant to your questions.

---

## Phase 2 — Ask Clarifying Questions (One Round Only)

After analysis, identify gaps that would block correct manifest creation.

- Ask **at most 5 questions** in a single message.
- Only ask what is **critical and cannot be inferred** from the codebase or existing manifests.
- Number the questions.
- Do not ask about things already answerable from the project files.
- Do not split into multiple rounds — this is your only chance to ask.

Example format:

```
Before I create the manifest, I need a few things clarified:

1. Should the new `AuthService` require an injected `TokenStore` or create its own?
2. Is this a new module or does it extend an existing service?
3. Should error handling raise custom exceptions or use standard ones?
```

Wait for the user's response before proceeding.

---

## Phase 3 — Draft the Manifest

Using the analysis and answers, create a **draft manifest** in `manifests/<slug>.manifest.yaml`.

### Slug Convention

Use a semantic slug: `<type>-<short-description>.manifest.yaml`

Examples:
- `add-auth-service.manifest.yaml`
- `fix-token-expiry-check.manifest.yaml`
- `refactor-user-validation.manifest.yaml`

### Manifest Structure

```yaml
schema: "2"
goal: "Clear, one-sentence description of what this task delivers"
type: feature|fix|refactor
created: "<today's date>"
description: |
  Detailed explanation of the change, why it matters, and any context.
temptations:
  - risk: "Concrete shortcut or gaming pattern this task invites."
    instead: "Concrete procedure the implementer should follow instead."

files:
  create:                           # New files (Strict Mode)
    - path: path/to/new_file.py
      artifacts:
        - kind: class
          name: ClassName
        - kind: method
          name: method_name
          of: ClassName
          args:
            - name: param
              type: Type
          returns: ReturnType
        - kind: function
          name: func_name
          args:
            - name: param
              type: Type
          returns: ReturnType
        - kind: attribute
          name: attr_name
          of: ClassName
          type: Type
  edit:                             # Existing files (Permissive Mode)
    - path: path/to/existing.py
      artifacts:
        - kind: method
          name: new_method
          of: ExistingClass
  read:                             # Dependencies (paths only)
    - path/to/dependency.py
    - tests/existing_test.py
  delete:                           # Files to remove (if applicable)
    - path: path/to/remove.py
      reason: "Why this file is no longer needed"

validate:
  - pytest tests/path/to/test_file.py -v
```

### Artifact Declaration Rules

- **Public symbols only** (no `_` prefix). Private implementation is free.
- **`files.create`** = Strict Mode. Implementation must EXACTLY match declared artifacts.
- **`files.edit`** = Permissive Mode. Implementation must CONTAIN at least the declared artifacts.
- **`kind`** values: `class`, `function`, `method`, `attribute`, `interface`, `type`, `enum`, `namespace`
- **`of`** = parent class name (required for `method` and `attribute`)
- **`args`** = list of `{name, type}` (for `function` and `method`)
- **`returns`** = return type string (optional but recommended)

### Key Decisions During Drafting

### Temptations Section Rules

- Place `temptations` immediately after `description` when the task has known implementation risks.
- Include 3-5 task-specific entries for substantial work; omit it only when there are no meaningful task-specific risks.
- Every `risk` must pair with an `instead` procedure. Do not write bare prohibitions.
- Keep entries concrete enough to behave like lint rules, for example: "Do not import from `app._internal` in tests" paired with "Exercise behavior through `app.api.*`."
- Generic MAID rules belong in `CLAUDE.md` or the skill, not in each manifest.

1. **New file vs. edit existing?** If the artifact belongs in a new module, use `files.create`. If it extends existing code, use `files.edit`.

2. **What are the dependencies?** List all files the implementation needs to read under `files.read`. Include test files that will be referenced in `validate`.

3. **What is the minimal public API?** Declare only what external code needs. Internal helpers are not declared — the AI agent has freedom there.

4. **What tests prove it works?** The `validate` commands must reference behavioral tests that USE the declared artifacts.

5. **How could this plan be gamed?** Before finalizing, adversarially review the manifest and behavioral tests for likely shortcuts, private-state access, over-broad assertions, schema loosening, or implementation-coupled tests. Add or revise `temptations` entries until the clean path is explicit.

---

## Phase 4 — Draft Behavioral Tests

Write the behavioral test file(s) referenced in the manifest's `validate` commands.

### Behavioral Test Requirements

- Tests must **import and USE** every declared artifact from the manifest.
- Tests define the **behavioral contract** (WHAT it does), not the implementation (HOW it does it).
- Tests must be **deterministic and independent** of each other.
- Tests must cover **happy paths, edge cases, and failure conditions**.
- Tests should follow the project's testing conventions (see `docs/unit-testing-rules.md` if available).

### What Behavioral Tests Verify

| Artifact Kind | Test Verifies |
|---------------|---------------|
| `class` | Can be instantiated with expected args |
| `method` | Produces expected output for given inputs |
| `function` | Produces expected output for given inputs |
| `attribute` | Exists and has expected type/behavior |

### Anti-Pattern: Testing Implementation

**DO:** Test observable behavior (inputs → outputs, state changes, side effects)
**DON'T:** Test private methods, internal state, or implementation details

The behavioral tests constrain the AI agent's output while leaving implementation freedom.

---

## Phase 5 — Validate the Draft

Run the behavioral validation:

```bash
maid validate manifests/<slug>.manifest.yaml --mode behavioral
```

### If Validation Passes

Proceed to Phase 6 (approval).

### If Validation Fails

Iterate on the manifest and/or tests together:

1. Read the validation errors carefully.
2. Fix the issue — it could be in the manifest (wrong artifact declaration) or the tests (missing artifact usage).
3. Re-run validation.
4. Repeat until validation passes.

This is the **Planning Loop** — refine the contract until it is internally consistent.

---

## Phase 6 — Present for Approval

Once validation passes, show the user:

```
## Manifest Draft: manifests/<slug>.manifest.yaml

**Goal:** <goal text>
**Type:** <type>

### Files
- Create: <list>
- Edit: <list>
- Read: <list>

### Declared Artifacts
<brief summary of artifacts>

### Validation
✅ Schema: valid
✅ Behavioral: tests reference all declared artifacts
✅ Commands: `maid validate manifests/<slug>.manifest.yaml --mode behavioral`

The manifest and behavioral tests are ready.
Reply YES to approve and proceed to implementation, or tell me what to change.
```

---

## Phase 7 — Revision Loop (if needed)

If the user requests changes:

1. Ask targeted follow-up questions to resolve the disagreement.
2. Update the manifest and/or tests.
3. Re-run `maid validate --mode behavioral`.
4. Show the updated plan and ask for approval again.

Repeat until the user approves and validation passes.

---

## Phase 8 — Hand Off to Implementation

Once approved, the manifest is the contract. The implementation phase (handled by a developer skill or the AI agent directly) follows this loop:

1. Load ONLY the files declared in the manifest (`files.create`, `files.edit`, `files.read`).
2. Implement code to satisfy the behavioral tests.
3. Run implementation validation:
   ```bash
   maid validate manifests/<slug>.manifest.yaml --mode implementation
   ```
4. Run behavioral tests:
   ```bash
   maid test
   ```
5. Iterate until both pass.

### Post-Implementation

```bash
maid validate              # All manifests (with chain merging)
maid test                  # All validation commands
```

If both pass, the task is complete and ready for commit.

---

## Quick Reference

### Manifest vs. Plan Comparison

| Traditional Plan (markdown) | MAID Manifest (yaml) |
|------------------------------|----------------------|
| Free-form text | Structured schema |
| Human-readable only | Machine-validatable |
| Decays over time | Enforced on every change |
| No artifact tracking | Explicit public API contract |
| Approval is subjective | Approval is objective (validation passes) |
| Requires translation to code | IS the implementation contract |

### When to Use This Skill

- Starting a new feature
- Planning a bug fix
- Designing a refactor
- Onboarding existing code (`maid snapshot`)

### When NOT to Use This Skill

- Pure documentation changes (`.md` files only)
- Private implementation refactors (no public API change) — update existing tests instead
- Emergency hotfixes that will be properly manifested later
