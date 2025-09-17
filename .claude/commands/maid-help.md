---
description: Show MAID workflow commands and their usage
---

## MAID Workflow Commands

The following commands help you implement the Manifest-driven AI Development (MAID) methodology:

### 📝 `/generate-manifest [task-number] [goal]`
Generate a MAID manifest file that specifies what needs to be implemented.
Example: `/generate-manifest 003 "Add user authentication with JWT tokens"`

### 🧪 `/generate-tests [manifest-file]`
Generate comprehensive tests based on a manifest specification.
Example: `/generate-tests manifests/task-003.manifest.json`

### 🔨 `/implement [manifest-file]`
Implement code to satisfy manifest requirements and pass all tests.
Example: `/implement manifests/task-003.manifest.json`

### 🔧 `/refactor [file] [manifest-file]`
Refactor implementation while ensuring tests still pass and API remains unchanged.
Example: `/refactor src/auth.py manifests/task-003.manifest.json`

### 📊 `/improve-tests [test-file] [manifest-file]`
Enhance test coverage and update manifest to reflect complete requirements.
Example: `/improve-tests tests/test_auth.py manifests/task-003.manifest.json`

### ✅ `/validate-manifest [manifest-file] [--chain]`
Validate a manifest against schema and implementation using AST validator.
Example: `/validate-manifest manifests/task-003.manifest.json --chain`

### 🧪 `/run-validation [manifest-file | task-number]`
Run validation tests for a specific task or manifest.
Example: `/run-validation 003` or `/run-validation manifests/task-003.manifest.json`

### 📈 `/maid-status`
Show comprehensive MAID project status including all manifests, tests, and implementations.
Example: `/maid-status`

## Workflow Process:

1. **Define Requirements**: Use `/generate-manifest` to create a specification
2. **Create Tests**: Use `/generate-tests` to create test suite from manifest
3. **Implement Solution**: Use `/implement` to write code that passes tests
4. **Refactor Code**: Use `/refactor` to improve code quality
5. **Enhance Testing**: Use `/improve-tests` to increase coverage and robustness

## Validation Tools:

- **Schema Validation**: `validate_schema(manifest_data, schema_path)`
- **AST Validation**: `validate_with_ast(manifest_data, implementation_file)`
- **Test Execution**: `PYTHONPATH=. uv run pytest [test-file]`

## Automatic Validation:

**Stop Hooks** are configured to automatically validate your project:
- **AST Validator Hook**: Runs on every Claude stop to check manifest-implementation alignment
- **Test Runner Hook**: Runs all tests automatically when Claude finishes responding
- **Auto-blocking**: Claude is prevented from stopping if validation fails
- See `.claude/hooks/README.md` for details

These commands and hooks ensure alignment between specifications (manifests), tests, and implementation!