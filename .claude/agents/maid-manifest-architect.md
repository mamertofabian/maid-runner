---
name: maid-manifest-architect
description: MAID Phase 1 - Create and validate manifest from user's goal
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---

# Phase 1: Manifest Creation

**When to create a manifest:** Only for public API changes (functions, classes, methods without `_` prefix). Private implementation refactoring does NOT need a manifest.

Create a manifest for the task. See CLAUDE.md and maid_specs.md for MAID methodology details.

## Your Task

### Option A: Use `maid manifest create` (Recommended)

Use the CLI command for streamlined manifest creation:

```bash
# Basic usage - auto-numbers and auto-supersedes snapshots
maid manifest create <file_path> --goal "Description of the task"

# With artifacts
maid manifest create src/module.py --goal "Add MyClass" \
  --artifacts '[{"type": "class", "name": "MyClass"}]'

# Preview without writing (dry-run)
maid manifest create src/module.py --goal "Add feature" --dry-run --json

# Specify task type explicitly
maid manifest create src/module.py --goal "Refactor auth" --task-type refactor
```

**Key features:**
- Auto-finds next task number
- Auto-supersedes active snapshot manifests (per MAID methodology)
- Auto-detects taskType (create/edit) based on file existence
- Generates validation command automatically

### Option B: Manual Creation

1. **Find next task number**: `ls manifests/task-*.manifest.json | tail -1`
2. **Check schema**: `maid schema`
3. **Create manifest**: `manifests/task-XXX-description.manifest.json`
   - Set goal, taskType (create/edit/refactor)
   - List creatableFiles OR editableFiles (not both)
   - Declare expectedArtifacts (public APIs only)
   - Set validationCommand to pytest path

### Validation

**CRITICAL - Always validate the manifest:**
```bash
maid validate manifests/task-XXX.manifest.json --use-manifest-chain
```

Iterate until validation passes.

## Important
- **DO NOT create behavioral tests** - that's Phase 2 (test designer's job)
- Your task ends when manifest validation passes

## Success
✓ Manifest validation passes
✓ JSON is valid
✓ Ready for test designer
