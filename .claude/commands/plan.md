---
description: Complete Phase 1 & 2 (manifest + tests) from goal
argument-hint: [goal description]
---

Create complete plan for: $ARGUMENTS

Use the maid-manifest-architect and maid-test-designer subagents to:

1. Phase 1: Create manifest
2. Phase 2: Create behavioral tests that USE artifacts
3. Validate behavioral: `maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain`
4. Verify Red phase: tests fail appropriately

Output: Ready-to-implement manifest + tests
