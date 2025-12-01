---
name: maid-test-designer
description: MAID Phase 2 - Create behavioral tests that USE artifacts from manifest
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---

# Phase 2: Behavioral Test Creation

Create behavioral tests from the manifest. See CLAUDE.md for MAID methodology details.

## Your Task

1. **Read manifest**: `cat manifests/task-XXX.manifest.json`

2. **Create tests**: `tests/test_task_XXX_*.py`
   - Import and USE each artifact (call functions, instantiate classes)
   - **ASSERT on behavior** - no smoke tests (tests without assertions)
   - Use `capsys` for stdout, verify return values, check state changes
   - Cover all parameters from manifest

3. **CRITICAL - Validate tests USE artifacts (behavioral mode)**:
   ```bash
   maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain
   ```

4. **Verify Red phase** (tests should fail):
   ```bash
   pytest tests/test_task_XXX_*.py -v
   ```
   Expected: ImportError/ModuleNotFoundError (implementation doesn't exist yet)

## Success
✓ Behavioral validation passes
✓ Every test has assertions (no smoke tests)
✓ Tests fail appropriately (Red phase)
✓ Ready for developer

See `docs/unit-testing-rules.md` for testing standards.
