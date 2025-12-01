---
description: Run code quality checks, fix issues, and commit changes
argument-hint: [optional: commit message]
---

Run quality checks, fix issues, and commit: $ARGUMENTS

This command performs a complete code quality workflow following the commit policy:

1. **Run all validation and quality checks:**
   ```bash
   uv run maid validate    # Validate all MAID manifests
   uv run maid test        # Run all MAID validation commands
   make lint               # Check code style with ruff
   make type-check         # Check type hints with ruff
   make test               # Run full pytest suite
   make format             # Format code with black
   ```

2. **Fix any auto-fixable issues:**
   ```bash
   make lint-fix           # Auto-fix linting issues
   ```

3. **Re-run checks after fixes to ensure all pass:**
   ```bash
   make lint               # Verify linting passes
   make type-check         # Verify type checking passes
   ```

4. **Show what will be committed:**
   ```bash
   git status
   git diff --staged
   git diff
   ```

5. **Commit the changes:**
   ```bash
   git add -A
   git commit -m "$ARGUMENTS" || git commit -m "chore: fix code quality issues"
   ```

**Note:** This command will commit changes automatically. It follows the commit policy by running all required validation checks first. If any checks fail, the commit will not proceed. If you need to run checks without committing, use the `fix` command instead.

