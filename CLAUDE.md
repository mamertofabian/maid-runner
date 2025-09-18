# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAID Runner is an implementation of the Manifest-driven AI Development (MAID) methodology. This project validates that code artifacts match their declarative manifests, ensuring AI-generated code aligns with architectural specifications.

## Architecture

### Core Components

1. **Manifest Validator** (`validators/manifest_validator.py`)
   - Validates manifest JSON against schema
   - AST-based validation to verify expected artifacts exist in code
   - Supports manifest chaining for tracking file evolution

2. **Manifest Schema** (`validators/schemas/manifest.schema.json`)
   - Defines the structure for task manifests
   - Specifies artifact types: class, function, attribute, parameter

3. **Manifest Files** (`manifests/`)
   - Chronologically ordered task definitions (task-001, task-002, etc.)
   - Each manifest is an immutable record of a single change

### Key Design Patterns

- **Migration Pattern**: Codebase state is the result of applying sequential manifests
- **Merging Validator**: Aggregates expected artifacts from all manifests that touched a file
- **Strict Validation**: Public interfaces must exactly match manifest declarations

## Common Development Commands

```bash
# Run all tests (python -m pytest automatically handles module paths)
uv run python -m pytest tests/ -v

# Run specific test file
uv run python -m pytest tests/test_manifest_validator.py -v

# Run tests for a specific integration task
uv run python -m pytest tests/test_task_001_integration.py -v

# Format code with black
uv run black .

# Lint code with ruff
uv run ruff check .

# Fix linting issues automatically
uv run ruff check --fix .
```

## Testing Strategy

Tests are organized by component:
- `test_manifest_validator.py` - Schema validation tests
- `test_ast_validator.py` - AST-based artifact validation
- `test_manifest_merger.py` - Manifest chain merging logic
- `test_task_XXX_integration.py` - End-to-end validation for each task manifest

## Important Implementation Notes

1. **Running Tests**: Use `uv run python -m pytest` to run tests - this automatically handles module imports correctly

2. **Artifact Validation**: The validator strictly enforces that:
   - All expected public artifacts exist
   - No unexpected public artifacts are present
   - Private artifacts (prefixed with `_`) are allowed without declaration

3. **Manifest Chain**: When `use_manifest_chain=True`, the validator discovers all manifests that touched a file and merges their expected artifacts chronologically

## MAID Methodology Context

This project implements the MAID specification from `docs/maid_specs.md`. Key principles:
- Explicitness over implicitness
- Extreme isolation of tasks
- Test-driven validation
- Directed dependency flow
- Verifiable chronology of changes