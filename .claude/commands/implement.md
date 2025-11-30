---
description: Implement code from manifest (Phase 3)
argument-hint: [manifest-path]
---

Implement: $1

Use the maid-developer subagent to:

1. Confirm Red phase: tests fail
2. Implement code to make tests pass
3. **CRITICAL - Validate ALL (no arguments)**:
   ```
   maid validate
   maid test
   make lint
   make type-check
   make test
   ```
4. Refactor if needed

See CLAUDE.md for TDD workflow.
