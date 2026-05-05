---
name: maid-implementer
description: Implement code against an approved MAID manifest. Loads only the declared files, writes code to pass behavioral tests, validates with maid validate --mode implementation, and iterates until all checks pass. Use after a manifest is approved by maid-planner (or manually).
---

# MAID Implementer Skill

## Rules

- ONLY load files declared in the manifest (`files.create`, `files.edit`, `files.read`).
- NEVER modify files not listed in the manifest.
- NEVER change the manifest during implementation. If the manifest is wrong, stop and flag it.
- NEVER skip validation. Both `maid validate --mode implementation` and `maid test` must pass.
- ALWAYS implement against the behavioral tests, not the manifest directly. The manifest declares WHAT exists; the tests define HOW it behaves.
- PRIVATE implementation is free. Refactor internals freely as long as public API and tests remain intact.

---

## Prerequisites

Verify the environment and manifest:

```bash
which maid 2>/dev/null || pip show maid-runner 2>/dev/null
maid validate manifests/<slug>.manifest.yaml --mode behavioral
```

If behavioral validation fails, **do not proceed**. The contract is not valid. Tell the user to run `maid-planner` to fix the manifest and tests first.

---

## Phase 1 — Load the Contract

Read the approved manifest and understand the scope:

```bash
cat manifests/<slug>.manifest.yaml
```

### Extract the Implementation Checklist

From the manifest, identify:

| Section | Action |
|---------|--------|
| `files.create` | Create these files with EXACTLY the declared artifacts (Strict Mode) |
| `files.edit` | Add/modify these files to INCLUDE the declared artifacts (Permissive Mode) |
| `files.read` | Load these for context — do NOT modify |
| `temptations` | Restate the relevant risk/procedure pairs before editing |
| `validate` | These commands must pass when done |

If the manifest includes `temptations`, identify which entries apply to the current edit and restate them as working constraints before implementation. Treat each `instead` value as the procedure to follow when test pressure points toward the paired shortcut.

### Load Dependencies

Read every file listed in `files.read`. This is your complete context — nothing more, nothing less.

---

## Phase 2 — Implement Against Behavioral Tests

### Strategy

1. Read the behavioral test file(s) from the `validate` commands.
2. Understand what behavior each test expects (inputs, outputs, error conditions).
3. Write the implementation to satisfy those tests.
4. The manifest artifacts are your structural requirements; the tests are your behavioral requirements. Both must be satisfied.

### For `files.create` (Strict Mode)

- Create the file from scratch.
- Declare **only** the public artifacts listed in the manifest.
- Add private helpers (`_` prefix) as needed — they are not validated by the manifest.
- Do NOT add extra public symbols. Strict Mode will reject them.

### For `files.edit` (Permissive Mode)

- Open the existing file.
- Add the new artifacts declared in the manifest.
- Existing code is preserved — Permissive Mode only checks that the new artifacts exist.
- You may modify existing code if the behavioral tests require it, but be conservative.

### Implementation Guidelines

**Follow the tests, not your instincts.** The behavioral tests define the contract. If a test expects `AuthService.login("user", "pass")` to return a `Token`, implement exactly that. The internal mechanism (hashing, storage, validation) is your choice.

**Handle errors explicitly.** If the behavioral tests assert exceptions, raise them. If they assert return values, return them. Match the test expectations precisely.

**Keep it simple first.** Write the minimal implementation that passes the tests. Refactor in Phase 4 if needed.

---

## Phase 3 — Validate Implementation

Run both validation checks:

```bash
# 1. Structural validation — does the code define the declared artifacts?
maid validate manifests/<slug>.manifest.yaml --mode implementation

# 2. Behavioral validation — do the tests pass?
maid test --manifest manifests/<slug>.manifest.yaml
```

### If Both Pass

Proceed to Phase 4 (refactoring) or Phase 5 (integration).

### If Structural Validation Fails

Read the errors carefully. Common issues:

| Error | Fix |
|-------|-----|
| `Artifact 'X' not found in file Y` | Add the missing public symbol |
| `Extra public artifact 'Z' in strict file Y` | Make it private (add `_` prefix) or add to manifest |
| `Signature mismatch for 'X'` | Match the declared args/returns exactly |
| `File Y not found` | Create the file (check path spelling) |

Fix the code, re-run validation, repeat.

### If Behavioral Tests Fail

Read the test output. Common issues:

| Issue | Fix |
|-------|-----|
| `AssertionError: expected X, got Y` | Fix the logic to produce correct output |
| `AttributeError: 'Class' has no attr 'X'` | Add the missing attribute |
| `TypeError: unexpected keyword` | Match the function signature the test expects |
| Import error | Check that imports match the actual module structure |

Fix the code, re-run tests, repeat.

---

## Phase 4 — Refactoring (Optional)

Once both validations pass, improve code quality **without changing the public API**:

- Extract helper functions (private, `_` prefix)
- Rename private variables for clarity
- Split long functions into smaller ones
- Add type hints to private code
- Improve error messages
- Optimize algorithms

### Refactoring Rules

1. **Public API is frozen.** No changes to public function signatures, class names, or exposed attributes.
2. **Tests must still pass.** Run after each refactoring step.
3. **Structural validation must still pass.** Run after each refactoring step.
4. **No manifest changes needed.** Private refactoring does not require a new manifest.

Validate after refactoring:

```bash
maid validate manifests/<slug>.manifest.yaml --mode implementation
maid test --manifest manifests/<slug>.manifest.yaml
```

---

## Phase 5 — Integration

Verify the change works within the full codebase:

```bash
# Validate ALL manifests (with chain merging)
maid validate

# Run ALL validation commands from active manifests
maid test
```

### If Full Validation Passes

The task is complete. Present the summary to the user:

```
## Implementation Complete: manifests/<slug>.manifest.yaml

**Goal:** <goal text>
**Status:** ✅ All validations passed

### Changes
- Created: <files.create list>
- Modified: <files.edit list>
- Tests: <validate commands>

### Validation
✅ Structural: all artifacts defined
✅ Behavioral: all tests passing
✅ Integration: all manifests valid (with chain merging)

Ready for commit.
```

### If Full Validation Fails

The implementation broke something elsewhere. Diagnose:

1. Did chain merging reveal a conflict with a prior manifest?
2. Did a dependency change break another module's tests?
3. Is there a coherence violation (naming, duplicates, boundaries)?

Fix the issue, re-run full validation, repeat.

---

## Error Recovery

### Manifest is Wrong

If you discover the manifest declares something that cannot be implemented as written (e.g., the test expects a signature that contradicts the artifact declaration):

1. **Stop.** Do not work around it.
2. Tell the user exactly what is inconsistent.
3. Suggest using `maid-planner` to revise the manifest.

### Tests are Wrong

If the behavioral tests assert behavior that contradicts the manifest's goal or is impossible to implement:

1. **Stop.** Do not implement impossible behavior.
2. Tell the user exactly what is wrong.
3. Suggest using `maid-planner` to revise the tests.

### Discovery: Missing Prerequisite

If implementation requires a capability that doesn't exist in the codebase (e.g., a validator check that maid-runner itself doesn't support):

1. **Stash current work:** `git stash`
2. Tell the user about the prerequisite gap
3. Create a separate manifest to fix the prerequisite
4. Complete the prerequisite (full MAID workflow)
5. **Restore and continue:** `git stash pop`

Never leave a task partially complete.

---

## Quick Reference

### Validation Commands

```bash
# Structural: does code match manifest?
maid validate manifests/<slug>.manifest.yaml --mode implementation

# Behavioral: do tests pass?
maid test --manifest manifests/<slug>.manifest.yaml

# Full codebase: everything
maid validate
maid test

# With coherence (architectural checks)
maid validate --coherence
```

### Mode Comparison

| Mode | Checks | When |
|------|--------|------|
| `behavioral` | Tests USE declared artifacts | Planning phase (maid-planner) |
| `implementation` | Code DEFINES declared artifacts | Implementation phase (this skill) |

### Strict vs. Permissive

| Mode | File Type | Rule |
|------|-----------|------|
| Strict | `files.create` | Public API must EXACTLY match manifest |
| Permissive | `files.edit` | Public API must CONTAIN manifest artifacts |

### When to Use This Skill

- After `maid-planner` produces an approved manifest
- When implementing a manually-written manifest
- When picking up an unimplemented manifest from the queue

### When NOT to Use This Skill

- Private-only refactors (no manifest needed, just update existing tests)
- Pure documentation changes
- When the manifest hasn't been validated behaviorally yet
