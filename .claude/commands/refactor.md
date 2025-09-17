---
description: Refactor implementation while maintaining test compliance
argument-hint: [file-to-refactor] [manifest-file-path]
allowed-tools: Edit, Read, Bash(pytest*), Bash(black*), Bash(ruff*)
---

## Task: Refactor Code While Maintaining Tests

Refactor the implementation in $1 according to manifest: $2

### Refactoring Goals:

1. **Code Quality Improvements:**
   - Extract common patterns into helper functions
   - Improve variable and function names for clarity
   - Reduce code duplication (DRY principle)
   - Simplify complex logic
   - Add or improve type hints
   - Enhance error handling

2. **Performance Optimization:**
   - Optimize algorithms and data structures
   - Reduce unnecessary iterations
   - Cache computed values when appropriate
   - Minimize I/O operations

3. **Maintainability:**
   - Split large functions into smaller, focused ones
   - Organize code into logical sections
   - Improve code documentation (docstrings)
   - Follow established design patterns

### Constraints:

- **DO NOT change the public API** - all artifacts in the manifest must remain unchanged:
  - Keep the same class names and inheritance
  - Keep the same function names and parameters
  - Keep the same attribute names and accessibility
- **ALL tests must continue to pass** after refactoring
- **Maintain backward compatibility**

### Process:

1. Run tests before refactoring to establish baseline
2. Read and understand the current implementation
3. Identify areas for improvement
4. Make incremental changes, testing after each change
5. Run code formatters (black) and linters (ruff)
6. Validate against the manifest using AST validator
7. Ensure all tests still pass

### Quality Checks:

- [ ] All tests pass (run validation command)
- [ ] Code is properly formatted (black)
- [ ] No linting errors (ruff)
- [ ] Public API unchanged (manifest validation)
- [ ] Code is more readable and maintainable
- [ ] Performance is same or better

### Commands to Run:

```bash
# Before refactoring
PYTHONPATH=. uv run pytest $VALIDATION_COMMAND

# After refactoring
uv run black $1
uv run ruff check $1
PYTHONPATH=. uv run pytest $VALIDATION_COMMAND
```

Remember: The goal is to improve the internal quality without changing external behavior!