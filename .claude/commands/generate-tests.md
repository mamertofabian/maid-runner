---
description: Generate behavioral tests from manifest (Phase 2)
argument-hint: [manifest-path]
---

Generate tests for manifest: $1

Invokes maid-test-designer agent to:

1. Read manifest expectedArtifacts
2. Create `tests/test_task_XXX_*.py`
3. Tests must USE artifacts (call functions, instantiate classes)
4. Validate: `maid validate $1 --validation-mode behavioral --use-manifest-chain`
5. Verify Red phase: `pytest tests/test_task_XXX_*.py -v`

See CLAUDE.md for behavioral testing patterns.
