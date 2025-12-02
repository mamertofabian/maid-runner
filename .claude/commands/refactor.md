---
description: Refactor code while maintaining compliance (Phase 3.5)
argument-hint: [file-path or task-number]
---

Refactor: $1

**Note:** Refactoring private implementation (functions/classes with `_` prefix) does NOT require a new manifest, as long as tests pass and public API is unchanged.

Use the maid-refactorer subagent to:

1. Ensure tests pass first
2. Refactor (remove duplication, improve naming, etc.)
3. **CRITICAL - Validate ALL after each change (no arguments)**:
   ```
   pytest tests/test_task_*_*.py -v
   maid validate
   maid test
   ```
4. Run quality checks: `make lint` and `make format`

Keep public API unchanged. See CLAUDE.md for complete refactoring guidelines.
