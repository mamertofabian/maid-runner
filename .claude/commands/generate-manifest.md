---
description: Generate MAID manifest from goal (Phase 1)
argument-hint: [goal description]
---

Create manifest for: $ARGUMENTS

**Note:** Manifests are only needed for public API changes. Private implementation refactoring doesn't require a manifest.

## Quick Method: Use `maid manifest create`

```bash
# Auto-numbers, auto-supersedes snapshots, auto-detects task type
maid manifest create <file_path> --goal "$ARGUMENTS"

# With artifacts
maid manifest create <file_path> --goal "$ARGUMENTS" \
  --artifacts '[{"type": "class", "name": "MyClass"}]'

# Preview first
maid manifest create <file_path> --goal "$ARGUMENTS" --dry-run --json
```

## Alternative: Use maid-manifest-architect subagent

For complex manifests or when you need more control, use the subagent to:

1. Analyze the goal and determine affected files
2. Use `maid manifest create` or create manifest manually
3. Validate: `maid validate manifests/task-XXX.manifest.json --use-manifest-chain`
4. Iterate until valid

**DO NOT create tests** - use /generate-tests for Phase 2.

See CLAUDE.md for manifest structure.
