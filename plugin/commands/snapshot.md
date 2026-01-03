---
description: Generate snapshot manifest from existing code to establish baseline for MAID tracking
---

# MAID Snapshot Command

Create a snapshot manifest from existing Python or TypeScript code.

## Purpose

Snapshots capture the current state of a file for MAID tracking:
- Establishes baseline for files that weren't created with MAID
- Freezes the public API at a point in time
- Auto-generates test stubs
- First step in migrating existing code to MAID

## Usage

```bash
# Basic snapshot
uv run maid snapshot $ARGUMENTS

# Skip test stub generation
uv run maid snapshot $ARGUMENTS --skip-test-stub

# Specify output directory
uv run maid snapshot $ARGUMENTS --output-dir manifests

# Force overwrite existing manifest
uv run maid snapshot $ARGUMENTS --force
```

## What Gets Captured

The snapshot includes:
- All **public** functions, classes, methods, attributes (no `_` prefix)
- Function signatures (args, return types)
- Class structures
- Module-level constants

## After Snapshot

Once a snapshot is created:
1. The file is considered "frozen"
2. Test stubs are generated automatically
3. Future changes require edit manifests
4. Editing will auto-supersede the snapshot

## Example Workflow

User: `/maid-runner:snapshot src/legacy_module.py`

1. Generate snapshot manifest
2. Show what was captured (functions, classes, etc.)
3. Indicate test stub location
4. Explain that future edits will supersede this snapshot

## Output

After creating snapshot:
- Path to created manifest
- Number of artifacts captured
- Test stub file path (if generated)
- Next steps: "To edit this file, use `maid manifest create` which will auto-supersede this snapshot"
