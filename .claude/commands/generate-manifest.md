---
description: Generate MAID manifest from goal (Phase 1)
argument-hint: [goal description]
---

Create manifest for: $ARGUMENTS

Use the maid-manifest-architect subagent to:

1. Find next task number
2. Create `manifests/task-XXX-description.manifest.json`
3. Validate: `maid validate manifests/task-XXX.manifest.json --use-manifest-chain`
4. Iterate until valid

See CLAUDE.md for manifest structure.
