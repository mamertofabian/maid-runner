---
description: Run complete MAID workflow from goal to validated implementation
argument-hint: [goal description]
---

Execute full MAID workflow for: $ARGUMENTS

This command orchestrates the complete MAID methodology from goal to validated, passing implementation.

## Workflow Phases

### Phase 1: Goal & Manifest Creation
Use the maid-manifest-architect subagent to:
1. Analyze the goal and identify affected files
2. Find next task number: `ls manifests/task-*.manifest.json | tail -1`
3. Create manifest: `manifests/task-XXX-description.manifest.json`
4. Validate structure: `maid validate manifests/task-XXX.manifest.json --use-manifest-chain`

### Phase 2: Test Design
Use the maid-test-designer subagent to:
1. Read manifest expectedArtifacts
2. Create behavioral tests: `tests/test_task_XXX_*.py`
3. Tests must USE artifacts AND ASSERT on behavior
4. Validate behavioral: `maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain`
5. Verify Red phase: `pytest tests/test_task_XXX_*.py -v` (tests should FAIL)

### Phase 3: Implementation
Use the maid-developer subagent to:
1. Confirm Red phase (tests fail)
2. Implement code to make tests pass
3. Run tests until Green: `pytest tests/test_task_XXX_*.py -v`
4. Validate implementation: `maid validate manifests/task-XXX.manifest.json --use-manifest-chain`

### Phase 3.5: Refactoring (if needed)
Use the maid-refactorer subagent to:
1. Improve code quality while tests pass
2. Run tests after each change
3. Keep public API unchanged

### Phase 4: Final Integration
Run complete validation to ensure no regressions:
```bash
maid validate    # Validate ALL manifests
maid test        # Run ALL validation commands
make lint        # Check code style
make type-check  # Check type hints
make test        # Run full test suite
```

## Success Criteria

- All behavioral tests pass
- Implementation validation passes
- No regressions in existing tests (`maid test` passes)
- Code quality checks pass

## Error Recovery

If validation fails at any phase, use the maid-fixer subagent to:
1. Identify the specific error
2. Fix one issue at a time
3. Re-validate after each fix

Output: Fully validated task with passing tests and clean code quality checks.
