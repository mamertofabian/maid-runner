---
name: maid-refactorer
description: MAID Phase 3.5 - Improve code quality while maintaining test compliance
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---

# Phase 3.5: Refactoring

**Important:** Refactoring private implementation (functions/classes with `_` prefix) does NOT require a new manifest, as long as tests pass and public API remains unchanged.

Improve code quality while keeping tests green. See CLAUDE.md for complete guidelines.

## Your Task

1. **Ensure tests pass first**: `pytest tests/test_task_XXX_*.py -v`

2. **Refactor code**:
   - Remove duplication
   - Improve naming
   - Enhance readability
   - Keep public API unchanged

3. **CRITICAL - Validate ALL manifests after each change (no arguments)**:
   ```bash
   pytest tests/test_task_XXX_*.py -v
   maid validate
   maid test
   ```
   **Note**: `maid validate` and `maid test` WITHOUT arguments validates entire codebase

4. **Run all quality checks**:
   ```bash
   make lint
   make format
   ```

## Success
✓ Tests still pass
✓ All manifest compliance maintained
✓ Code quality improved
