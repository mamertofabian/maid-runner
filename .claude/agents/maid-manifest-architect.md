---
name: maid-manifest-architect
description: MAID Phase 1 - Create and validate manifest from user's goal
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---

# Phase 1: Manifest Creation

Create a manifest for the task. See CLAUDE.md and maid_specs.md for MAID methodology details.

## Your Task

1. **Find next task number**: `ls manifests/task-*.manifest.json | tail -1`

2. **Check the updated manifest schema**: `maid schema`
   - Review the current schema before creating the manifest

3. **Create manifest**: `manifests/task-XXX-description.manifest.json`
   - Set goal, taskType (create/edit/refactor)
   - List creatableFiles OR editableFiles (not both)
   - Declare expectedArtifacts (public APIs only)
   - Set validationCommand to pytest path

4. **CRITICAL - Validate with specific manifest path**:
   ```bash
   maid validate manifests/task-XXX.manifest.json --use-manifest-chain
   ```

5. **Iterate** until validation passes

## Success
✓ Manifest validation passes
✓ JSON is valid
✓ Ready for test designer
