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

1. **Create Manifest Using CLI** (`manifests/task-XXX.manifest.json`)
   ```bash
   # Use the CLI to create manifest - handles numbering, supersession automatically
   uv run maid manifest create <file-path> \
     --goal "Clear description of what this task accomplishes" \
     --artifacts '[{"type":"function","name":"my_func","args":[{"name":"arg1","type":"str"}],"returns":"str"}]'

   # Preview first with --dry-run
   uv run maid manifest create <file-path> \
     --goal "..." \
     --artifacts '[...]' \
     --dry-run
   ```

   **CLI Benefits:**
   - ✅ Auto-numbers tasks (finds next available)
   - ✅ Auto-detects taskType (create/edit based on file existence)
   - ✅ Auto-supersedes snapshots when editing frozen code
   - ✅ Auto-generates test file path
   - ✅ Validates against schema

   **For multi-file tasks:** Create separate manifests for each file

2. **Generate Test Stubs** (`tests/test_task_XXX_*.py`)
   ```bash
   # Auto-generate failing test stubs from manifest
   uv run maid generate-stubs manifests/task-XXX.manifest.json
   ```

   Then:
   - Review generated stubs
   - Enhance tests to fully USE the declared artifacts
   - Add assertions and test cases
   - Follow TDD: Tests should fail now, pass after implementation

3. **Validate Behavioral Compliance**
   ```bash
   uv run maid validate manifests/task-XXX.manifest.json \
     --validation-mode behavioral \
     --use-manifest-chain
   ```

   Fix until tests properly use all declared artifacts

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

## CLI Commands Quick Reference

```bash
# Create manifest (auto-numbers, auto-supersedes)
uv run maid manifest create <file-path> --goal "..." --artifacts '[...]'

# Generate test stubs
uv run maid generate-stubs manifests/task-XXX.manifest.json

# Validate (behavioral mode for Phase 2)
uv run maid validate <manifest> --validation-mode behavioral --use-manifest-chain

# Validate (implementation mode for Phase 3)
uv run maid validate <manifest> --validation-mode implementation --use-manifest-chain

# Run tests
uv run maid test --manifest <manifest>

# Check file tracking
uv run maid files --issues-only

# Create snapshot of existing code
uv run maid snapshot <file-path>

# Initialize MAID in new project
uv run maid init
```

## Progressive Disclosure

For detailed information:
- **Manifest structure**: See [MANIFEST_GUIDE.md](MANIFEST_GUIDE.md)
- **Validation details**: See [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md)
- **Full methodology**: See [MAID_SPECS.md](MAID_SPECS.md)

## Common Patterns (Using CLI)

### Creating a New File
```bash
# CLI auto-detects taskType="create" for non-existent files
uv run maid manifest create src/new_module.py \
  --goal "Add new payment processing module" \
  --artifacts '[
    {"type":"function","name":"process_payment","args":[{"name":"amount","type":"Decimal"}],"returns":"PaymentResult"}
  ]'
```

### Editing an Existing File
```bash
# CLI auto-detects taskType="edit" for existing files
# Auto-supersedes snapshots if file was frozen
uv run maid manifest create src/existing_module.py \
  --goal "Add refund support to payment module" \
  --artifacts '[
    {"type":"function","name":"process_refund","args":[{"name":"payment_id","type":"str"}],"returns":"RefundResult"}
  ]'
```

### Multi-File Feature (Separate Manifests)
```bash
# Create separate manifests for each file
uv run maid manifest create src/utils.py \
  --goal "Add utility functions" \
  --artifacts '[...]'

uv run maid manifest create src/handlers.py \
  --goal "Update request handlers" \
  --artifacts '[...]'
```

### Deleting a File
```bash
# Create deletion manifest (supersedes all active manifests for file)
uv run maid manifest create src/old_module.py \
  --goal "Remove deprecated module" \
  --delete
```

### Renaming a File
```bash
# Create rename manifest (supersedes all active manifests for source)
uv run maid manifest create src/old_name.py \
  --goal "Rename module for clarity" \
  --rename-to src/new_name.py \
  --artifacts '[...]'  # Same artifacts, new location
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
