---
name: maid-workflow
description: Enforces Manifest-driven AI Development (MAID) methodology for all code changes. Use when creating features, fixing bugs, refactoring code, or making any code modifications. Ensures manifest-first development with behavioral tests and validation.
allowed-tools: Read, Write, Edit, Bash(uv run maid:*), Bash(pytest:*), Bash(python -m pytest:*), Grep, Glob
---

# MAID Workflow Enforcement

**CRITICAL: Every code change in this project MUST follow the MAID workflow.**

## Quick Reference: MAID Workflow

### Phase 1: Goal Definition
Confirm the high-level goal before proceeding. Ensure you understand what needs to be accomplished.

### Phase 2: Planning Loop (BEFORE Implementation)
**Iterative refinement until validation passes:**

1. **Create Manifest** (`manifests/task-XXX.manifest.json`)
   - Define goal, files, and expected artifacts
   - Use `taskType`: "create", "edit", or "refactor"
   - **CRITICAL**: `expectedArtifacts` is an OBJECT for ONE file only
   - For multi-file changes: Create separate manifests

2. **Create Behavioral Tests** (`tests/test_task_XXX_*.py`)
   - Tests must USE the artifacts declared in manifest
   - Follow TDD: Write tests that will pass once implementation is complete

3. **Validate Behavioral Compliance**
   ```bash
   uv run maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain
   ```

4. **Refine** manifest and tests together until validation passes

### Phase 3: Implementation

1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run implementation validation:
   ```bash
   uv run maid validate manifests/task-XXX.manifest.json --validation-mode implementation --use-manifest-chain
   ```
4. Run behavioral tests from manifest's `validationCommand`
5. Iterate until all validations and tests pass

### Phase 4: Integration

Verify complete compliance:
```bash
# Validate all manifests
uv run maid validate

# Run all MAID validation commands
uv run maid test

# Run full test suite
uv run python -m pytest tests/ -v
```

## Manifest Structure

**Template for new manifests:**

```json
{
  "goal": "Clear, specific description of what this task accomplishes",
  "taskType": "create|edit|refactor",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "path/to/single/file.py",
    "contains": [
      {
        "type": "function",
        "name": "function_name",
        "args": [{"name": "arg1", "type": "str"}],
        "returns": "ReturnType"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_task_XXX_*.py", "-v"]
}
```

## Key Rules

**NEVER:**
- Modify code without a manifest
- Skip validation steps
- Access files not listed in manifest
- Put multiple files in `expectedArtifacts` (it's an OBJECT, not array)

**ALWAYS:**
- Manifest first, then tests, then implementation
- Validate before and after changes
- Use `--use-manifest-chain` for edit tasks
- Ensure public APIs (no `_` prefix) are in manifest

## Artifact Types

```json
// Function
{"type": "function", "name": "my_func", "args": [...], "returns": "str"}

// Class
{"type": "class", "name": "MyClass"}

// Method
{"type": "function", "name": "my_method", "class": "MyClass", "args": [...]}

// Attribute
{"type": "attribute", "name": "my_attr", "class": "MyClass"}

// Module-level attribute
{"type": "attribute", "name": "MY_CONSTANT"}
```

## Validation Modes

- **Behavioral Mode** (`--validation-mode behavioral`): Checks tests USE artifacts
  - Use during Phase 2 when writing tests

- **Implementation Mode** (`--validation-mode implementation`): Checks code DEFINES artifacts
  - Use during Phase 3 when implementing code
  - Includes file tracking analysis with `--use-manifest-chain`

## Finding Next Task Number

```bash
# Find the last task number
ls manifests/task-*.manifest.json | tail -1

# Next task is +1 from the last number
```

## Progressive Disclosure

For detailed information:
- **Manifest structure**: See [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)
- **Validation details**: See [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md)
- **Full methodology**: See [MAID_SPECS.md](MAID_SPECS.md)

## Common Patterns

### Creating a New File
```json
{
  "taskType": "create",
  "creatableFiles": ["src/new_module.py"],
  "expectedArtifacts": {
    "file": "src/new_module.py",
    "contains": [...]
  }
}
```

### Editing an Existing File
```json
{
  "taskType": "edit",
  "editableFiles": ["src/existing_module.py"],
  "expectedArtifacts": {
    "file": "src/existing_module.py",
    "contains": [/* only NEW or MODIFIED artifacts */]
  }
}
```

### Multi-File Feature (Separate Manifests)
```bash
# Wrong: One manifest with multiple files in expectedArtifacts
# Right: Separate manifests
manifests/task-050-add-utils.manifest.json      # Modifies utils.py
manifests/task-051-update-handlers.manifest.json # Modifies handlers.py
```

## Definition of Done

A task is complete when ALL of these pass:
- ✅ Behavioral validation passes
- ✅ Implementation validation passes
- ✅ All tests from `validationCommand` pass
- ✅ `uv run maid validate` passes
- ✅ `uv run maid test` passes

**Zero tolerance**: Fix ALL errors before proceeding to next task.

## Refactoring Private Implementation

Private code (functions/classes with `_` prefix) can be refactored freely without new manifests, as long as:
- All tests continue to pass
- All validations pass
- Public API remains unchanged
- No MAID rules are violated

This allows practical development without bureaucracy while maintaining accountability for public interface changes.
