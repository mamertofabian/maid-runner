---
description: Fix validation errors and test failures (Phase 3 support)
argument-hint: [optional: specific error context]
---

Fix errors: $ARGUMENTS

Use the maid-fixer subagent to:

1. Collect errors: `maid validate` and `maid test`
2. Fix one issue at a time
3. **CRITICAL - Validate ALL after each fix (no arguments)**:
   ```
   maid validate
   maid test
   ```
4. Repeat until all errors resolved

See CLAUDE.md for common error patterns.
