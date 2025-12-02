---
description: Generate MAID manifest from goal (Phase 1)
argument-hint: [goal description]
---

Create manifest for: $ARGUMENTS

**Note:** Manifests are only needed for public API changes. Private implementation refactoring doesn't require a manifest.

Use the maid-manifest-architect subagent to:

1. Find next task number
2. Create `manifests/task-XXX-description.manifest.json`
3. Validate: `maid validate manifests/task-XXX.manifest.json --use-manifest-chain`
4. Iterate until valid

**DO NOT create tests** - use /generate-tests for Phase 2.

See CLAUDE.md for manifest structure.
