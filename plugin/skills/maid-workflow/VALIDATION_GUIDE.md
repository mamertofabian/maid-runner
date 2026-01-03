# MAID Validation Guide

## Overview

MAID validation operates in two distinct modes, each serving a specific phase of development:

1. **Behavioral Mode**: Validates that tests USE the declared artifacts (Phase 2)
2. **Implementation Mode**: Validates that code DEFINES the declared artifacts (Phase 3)

## CLI Features & Options

The `maid validate` command provides powerful features for different workflows:

### Watch Modes (Live TDD)

```bash
# Watch single manifest (re-validate on changes)
uv run maid validate <manifest> --watch

# Watch all manifests (validate affected on changes)
uv run maid validate --watch-all
```

### Performance Optimization

```bash
# Enable caching for faster validation
uv run maid validate --use-cache

# Manifest chain caching improves performance when validating multiple times
```

### Schema-Only Validation

```bash
# Quick schema check without AST parsing
uv run maid validate <manifest> --validation-mode schema
```

### Output Control

```bash
# Quiet mode (errors only)
uv run maid validate --quiet

# Verbose mode (detailed output)
uv run maid validate --verbose
```

### Directory Validation

```bash
# Validate all manifests in directory
uv run maid validate --manifest-dir manifests

# Automatically enables --use-manifest-chain and file tracking
```

## Validation Modes

### Behavioral Mode (Phase 2: Planning Loop)

**Purpose**: Ensure tests reference and use the artifacts declared in the manifest

**When to use**: During Phase 2 when writing behavioral tests

**Command:**
```bash
uv run maid validate manifests/task-XXX.manifest.json \
  --validation-mode behavioral \
  --use-manifest-chain
```

**What it checks:**
- ✅ Manifest conforms to JSON schema
- ✅ Test files exist and are readable
- ✅ Tests import and use declared artifacts
- ✅ All artifacts from manifest are referenced in tests

**Example failure:**
```
❌ Behavioral validation failed:
Test file tests/test_task_042_payment.py does not use artifact:
  - process_payment (function)

Expected: Test should import and call process_payment()
```

**Fix**: Add test that uses the artifact:
```python
def test_process_payment():
    result = process_payment(Decimal("100.00"), PaymentMethod.CARD)
    assert result.success
```

### Implementation Mode (Phase 3: Implementation)

**Purpose**: Ensure code defines the artifacts declared in the manifest

**When to use**: During Phase 3 when implementing code, and for final validation

**Command:**
```bash
uv run maid validate manifests/task-XXX.manifest.json \
  --validation-mode implementation \
  --use-manifest-chain
```

**What it checks:**
- ✅ Manifest conforms to JSON schema
- ✅ Code files exist and are readable
- ✅ Code defines all declared artifacts
- ✅ Artifact signatures match (function args, return types)
- ✅ File tracking analysis (undeclared/registered/tracked files)

**Validation strictness:**
- **creatableFiles**: Strict (must exactly match expectedArtifacts)
- **editableFiles**: Permissive (must contain expectedArtifacts, can have more)

**Example failure:**
```
❌ Implementation validation failed:
File src/payments.py missing required artifact:
  - process_refund (function with args: [{"name": "payment_id", "type": "str"}])

Expected: Function process_refund(payment_id: str) -> RefundResult
```

**Fix**: Implement the missing artifact:
```python
def process_refund(payment_id: str) -> RefundResult:
    # Implementation
    pass
```

## Manifest Chain Validation

**What is manifest chaining?**

When using `--use-manifest-chain`, MAID merges all non-superseded manifests for a file to build the complete expected state.

**Example:**
```
File: src/payments.py

task-042-add-payment.manifest.json
  └─ expectedArtifacts: process_payment

task-055-add-refund.manifest.json
  └─ expectedArtifacts: process_refund

With --use-manifest-chain:
  Merged artifacts = {process_payment, process_refund}
```

**When to use:**
- ✅ Always use for `taskType: "edit"` (editing existing files)
- ✅ When validating the entire codebase (`uv run maid validate`)
- ❌ Not needed for `taskType: "create"` (new files have no history)

**Command:**
```bash
uv run maid validate manifests/task-055-add-refund.manifest.json \
  --validation-mode implementation \
  --use-manifest-chain
```

This validates that `src/payments.py` contains BOTH `process_payment` (from task-042) and `process_refund` (from task-055).

## File Tracking Analysis

When using `--use-manifest-chain` in implementation mode, MAID performs file tracking analysis:

### Status Levels

**🔴 UNDECLARED (High Priority)**
- Files exist in codebase but not in any manifest
- No audit trail of when/why created
- **Action**: Add to `creatableFiles` or `editableFiles` in a manifest

**🟡 REGISTERED (Medium Priority)**
- Files in manifests but incomplete compliance
- Issues: Missing `expectedArtifacts`, no tests, or only in `readonlyFiles`
- **Action**: Add `expectedArtifacts` and `validationCommand`

**✅ TRACKED (Clean)**
- Files with full MAID compliance
- Properly documented with artifacts and tests

### Example Output

```
File Tracking Analysis:
  🔴 UNDECLARED (2 files):
    - src/helpers.py (no manifest)
    - src/legacy_utils.py (no manifest)

  🟡 REGISTERED (1 file):
    - src/config.py (in manifests but missing expectedArtifacts)

  ✅ TRACKED (15 files)
```

## Whole-Codebase Validation

### Validate All Manifests

```bash
# Validates ALL active manifests with proper chaining
uv run maid validate
```

**What it does:**
- Automatically excludes superseded manifests
- Uses manifest chain for each file
- Reports file tracking status
- Comprehensive validation across entire codebase

### Run All Validation Commands

```bash
# Runs ALL validation commands from active manifests
uv run maid test
```

**What it does:**
- Executes `validationCommand` from each active manifest
- Skips superseded manifests
- Reports test results for all tasks
- Ensures behavioral tests pass

## Common Validation Scenarios

### Scenario 1: New Feature (Create)

```bash
# 1. Phase 2: Validate tests use artifacts
uv run maid validate manifests/task-050-new-feature.manifest.json \
  --validation-mode behavioral

# 2. Phase 3: Validate code defines artifacts
uv run maid validate manifests/task-050-new-feature.manifest.json \
  --validation-mode implementation

# 3. Run behavioral tests
uv run python -m pytest tests/test_task_050_*.py -v
```

### Scenario 2: Editing Existing File

```bash
# 1. Phase 2: Validate tests (with chain context)
uv run maid validate manifests/task-051-update-feature.manifest.json \
  --validation-mode behavioral \
  --use-manifest-chain

# 2. Phase 3: Validate implementation (with chain)
uv run maid validate manifests/task-051-update-feature.manifest.json \
  --validation-mode implementation \
  --use-manifest-chain

# 3. Run behavioral tests
uv run python -m pytest tests/test_task_051_*.py -v
```

### Scenario 3: Complete Project Validation

```bash
# Validate all manifests
uv run maid validate

# Run all MAID tests
uv run maid test

# Run full test suite
uv run python -m pytest tests/ -v
```

## Troubleshooting Validation Errors

### Schema Validation Errors

```
❌ Schema validation failed:
  - expectedArtifacts.file: Required
```

**Fix**: Ensure manifest has all required fields

### Behavioral Validation Errors

```
❌ Test does not import artifact 'MyClass'
```

**Fix**: Add import and usage in test:
```python
from module import MyClass

def test_my_class():
    obj = MyClass()
    assert obj is not None
```

### Implementation Validation Errors

```
❌ Missing artifact: my_function
```

**Fix**: Implement the function in the file:
```python
def my_function(arg1: str) -> int:
    pass
```

### File Tracking Warnings

```
🔴 UNDECLARED: src/new_file.py
```

**Fix**: Create manifest for the file:
```json
{
  "goal": "Add new_file.py",
  "taskType": "create",
  "creatableFiles": ["src/new_file.py"],
  "expectedArtifacts": {
    "file": "src/new_file.py",
    "contains": [...]
  }
}
```

## Quick Reference Commands

```bash
# === Validation ===
# Behavioral validation (Phase 2)
uv run maid validate <manifest> --validation-mode behavioral --use-manifest-chain

# Implementation validation (Phase 3)
uv run maid validate <manifest> --validation-mode implementation --use-manifest-chain

# Validate all manifests (whole codebase)
uv run maid validate

# Schema-only validation (quick check)
uv run maid validate <manifest> --validation-mode schema

# === Watch Modes (Live TDD) ===
# Watch single manifest (validate on changes)
uv run maid validate <manifest> --watch

# Watch all manifests
uv run maid validate --watch-all

# === Testing ===
# Run all MAID tests (batch mode)
uv run maid test

# Run specific manifest tests
uv run maid test --manifest <manifest>

# Watch mode for tests
uv run maid test --manifest <manifest> --watch
uv run maid test --watch-all

# === File Tracking ===
# Check file status (quick, no validation)
uv run maid files --issues-only

# Show all tracked/untracked files
uv run maid files

# === Performance ===
# Enable caching for faster validation
uv run maid validate --use-cache
```

## Definition of Done Checklist

A task passes validation when:

- [ ] Behavioral validation passes
- [ ] Implementation validation passes
- [ ] Validation command tests pass
- [ ] `uv run maid validate` passes (whole codebase)
- [ ] `uv run maid test` passes (all MAID tests)
- [ ] No 🔴 UNDECLARED files introduced
- [ ] No 🟡 REGISTERED files left incomplete

**Zero tolerance for errors**: Fix all validation failures before proceeding.
