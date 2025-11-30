---
description: Generate MAID manifest from goal (Phase 1)
argument-hint: [goal description]
---

Create manifest for: $ARGUMENTS

Invokes maid-manifest-architect agent to:

1. Find next task number
2. Create `manifests/task-XXX-description.manifest.json`
3. Validate: `maid validate manifests/task-XXX.manifest.json --use-manifest-chain`
4. Iterate until valid

See CLAUDE.md for manifest structure.
