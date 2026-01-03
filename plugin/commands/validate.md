---
description: Validate all MAID manifests or a specific manifest with implementation and behavioral checks
---

# MAID Validation Command

Run comprehensive MAID validation for the current project or a specific manifest.

## Default Behavior

If no arguments provided, validate ALL active manifests:
```bash
uv run maid validate
```

## Specific Manifest Validation

If the user provides a manifest path as argument, validate that specific manifest:

**Implementation validation (default):**
```bash
uv run maid validate $ARGUMENTS --validation-mode implementation --use-manifest-chain
```

**Behavioral validation:**
```bash
uv run maid validate $ARGUMENTS --validation-mode behavioral --use-manifest-chain
```

## Report Results

After validation:
1. Show validation status (passed/failed)
2. List any errors or warnings
3. Display file tracking analysis if available
4. Suggest next steps if validation failed

## Example Usage

User: `/maid-runner:validate manifests/task-042-add-payment.manifest.json`

Run both behavioral and implementation validation, report results, and provide guidance on fixing any issues.
