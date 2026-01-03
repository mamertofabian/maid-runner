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

## Specific Manifest Testing

If the user provides a manifest path as argument:
```bash
uv run maid test --manifest $ARGUMENTS
```

## Watch Mode

For TDD workflow, offer watch mode:
```bash
# Single manifest watch
uv run maid test --manifest $ARGUMENTS --watch

# Multi-manifest watch (run affected tests on changes)
uv run maid test --watch-all
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
