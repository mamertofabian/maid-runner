---
description: Run MAID validation tests for all manifests or a specific manifest
---

# MAID Test Command

Run behavioral tests defined in manifest validation commands.

## Default Behavior

If no arguments provided, run ALL validation commands from all active manifests:
```bash
uv run maid test
```

This executes the `validationCommand` from each active manifest and reports results.

**Note:** Automatically uses **batch mode** when running multiple pytest tests (10-20x faster) by combining them into a single invocation.

## Specific Manifest Testing

If the user provides a manifest path as argument:
```bash
uv run maid test --manifest $ARGUMENTS
```

## Watch Mode (TDD Workflow)

For continuous testing during development:
```bash
# Single manifest watch (re-run tests on file changes)
uv run maid test --manifest $ARGUMENTS --watch

# Multi-manifest watch (run affected tests on changes)
uv run maid test --watch-all
```

## Additional Options

**Fail fast (stop on first failure):**
```bash
uv run maid test --fail-fast
```

**Verbose output (show detailed test output):**
```bash
uv run maid test --verbose
```

**Quiet mode (only show summary):**
```bash
uv run maid test --quiet
```

**Custom timeout:**
```bash
uv run maid test --timeout 600  # 10 minutes
```

## Report Results

After running tests:
1. Show test pass/fail summary
2. Display any test failures with details
3. Show which manifests passed/failed
4. Suggest fixes for failures

## Example Usage

User: `/maid-runner:test manifests/task-042-add-payment.manifest.json`

Run the validation command from task-042 manifest, show results, and provide guidance if tests fail.
