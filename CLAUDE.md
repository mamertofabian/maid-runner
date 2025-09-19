# CLAUDE.md

**⚠️ CRITICAL: This project dogfoods MAID v1.2. Every code change MUST follow the MAID workflow.**

## MAID Workflow (Required for ALL changes)

### Phase 1: Goal Definition
Confirm the high-level goal with user before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft behavioral tests (`tests/test_task_XXX_*.py`) - **PRIMARY CONTRACT**
2. Draft manifest (`manifests/task-XXX.manifest.json`) pointing to tests & declaring artifacts
3. Run structural validation (checks manifest↔tests AND implementation↔history):
   `uv run python validators/manifest_validator.py manifests/task-XXX.manifest.json --use-manifest-chain`
4. Refine BOTH tests & manifest together until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run behavioral validation (from `validationCommand`)
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `uv run python -m pytest tests/ -v`

## Project Overview

MAID Runner implements and enforces the Manifest-driven AI Development (MAID) methodology from `docs/maid_specs.md`. It validates that code artifacts match their declarative manifests, ensuring AI-generated code aligns with architectural specifications through strict chronological tracking.

## Architecture

### Core Components

1. **Manifest Validator** (`validators/manifest_validator.py`)
   - Validates manifest JSON against schema
   - AST-based validation to verify expected artifacts exist in code
   - Enforces manifest chain chronology

2. **Manifest Schema** (`validators/schemas/manifest.schema.json`)
   - Defines the required structure for task manifests
   - Artifact types: class, function, attribute, parameter

3. **Manifest Files** (`manifests/`)
   - Chronologically ordered, immutable task records
   - Sequential naming: task-001, task-002, task-003, etc.
   - Each represents a single atomic change

### Key MAID Principles in This Codebase

- **Explicitness**: Every task context is explicitly defined in manifests
- **Extreme Isolation**: Tasks touch minimal files, specified in manifest
- **Test-Driven Validation**: Tests define success, not subjective assessment
- **Verifiable Chronology**: Current state = sequential manifest application

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Tests first → Manifest → Implementation → Validate

## Validation Modes (MAID v1.2)

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)

## Manifest Template

```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],  // Optional: paths to obsolete manifests
  "creatableFiles": [],  // New files (Strict Mode)
  "editableFiles": [],   // Existing files (Permissive Mode)
  "readonlyFiles": [],   // Dependencies and tests
  "expectedArtifacts": {
    "file": "path/to/file.py",
    "contains": [
      {
        "type": "function|class|attribute",
        "name": "artifact_name",
        "class": "ParentClass",  // For methods/attributes
        "args": [{"name": "arg1", "type": "str"}],  // For functions
        "returns": "ReturnType"  // Optional
      }
    ]
  },
  "validationCommand": ["pytest tests/test_file.py -v"]
}
```

## Quick Commands

```bash
# Find next manifest number
ls manifests/task-*.manifest.json | tail -1

# Structural validation (pre-implementation)
uv run python validators/manifest_validator.py manifests/task-XXX.manifest.json --use-manifest-chain

# Behavioral validation (test execution)
uv run python -m pytest tests/test_task_XXX_integration.py -v

# Full test suite
uv run python -m pytest tests/ -v

# Code quality
uv run black . && uv run ruff check . --fix
```

## Artifact Rules

- **Public** (no `_` prefix): MUST be in manifest
- **Private** (`_` prefix): Optional in manifest
- **creatableFiles**: Strict validation (exact match)
- **editableFiles**: Permissive validation (contains at least)

## Key Reminders

- This codebase **IS** the MAID implementation - exemplify the methodology
- Manifest chain = source of truth for file state
- Tests = contracts, not suggestions
- Every change needs a manifest with sequential numbering