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

## Additional Options

**Watch mode (auto-revalidate on changes):**
```bash
# Watch single manifest
uv run maid validate $ARGUMENTS --watch

# Watch all manifests
uv run maid validate --watch-all
```

**Schema-only validation:**
```bash
uv run maid validate $ARGUMENTS --validation-mode schema
```

**Enable caching for faster performance:**
```bash
uv run maid validate $ARGUMENTS --use-cache
```

## Report Results

After validation:
1. Show validation status (passed/failed)
2. List any errors or warnings
3. Display file tracking analysis if available
4. Suggest next steps if validation failed
5. If watch mode requested, explain it will auto-rerun on changes

## Example Usage

User: `/maid-runner:validate manifests/task-042-add-payment.manifest.json`

Run both behavioral and implementation validation, report results, and provide guidance on fixing any issues.

User: `/maid-runner:validate --watch`

Set up watch mode for all manifests - auto-validates on file changes.
