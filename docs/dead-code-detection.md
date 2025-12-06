# Dead Code Detection with Vulture

This project uses [Vulture](https://github.com/jendrikseipp/vulture) to detect unused/dead code.

## Usage

```bash
# Standard scan (80% confidence threshold)
make dead-code

# Lower confidence (more results, more false positives)
uv run vulture maid_runner/ tests/ --min-confidence 60

# Higher confidence (fewer results, more accurate)
uv run vulture maid_runner/ tests/ --min-confidence 90

# Scan only source code (not tests)
uv run vulture maid_runner/ --min-confidence 80
```

## Understanding Results

Vulture assigns a confidence score (0-100%) to each finding:

- **90-100%**: Very likely dead code
- **80-89%**: Probably dead code
- **60-79%**: Possibly dead code (many false positives)
- **<60%**: High false positive rate

## Common False Positives

These are NOT dead code (configured in `.vulture` whitelist):

1. **AST Visitor Methods**: `visit_*` methods are called by `ast.NodeVisitor`
2. **Pytest Fixtures**: Functions used via dependency injection
3. **Magic Methods**: `__init__`, `__str__`, etc.
4. **CLI Entry Points**: `main()` called by setuptools
5. **Module Constants**: Exported for external use
6. **Mock Attributes**: `side_effect`, etc. used by pytest mocks
7. **TypedDict Fields**: Type definitions in `types.py`

## Handling False Positives

If vulture reports code that IS actually used:

### Option 1: Add to `.vulture` Whitelist

```bash
# Add specific function/class names
echo "my_function_name" >> .vulture

# Add patterns (e.g., all visit_ methods)
echo "visit_*" >> .vulture
```

### Option 2: Use Inline Comments

```python
def my_function():  # vulture: ignore
    """This function is used via reflection."""
    pass
```

## Real Dead Code Examples

Vulture can find:

- **Unused functions**: Defined but never called
- **Unused classes**: Defined but never instantiated
- **Unused methods**: Defined but never invoked
- **Unused imports**: Imported but never referenced
- **Unused variables**: Assigned but never read

## Integration Status

- ✅ Installed and configured
- ✅ Available via `make dead-code`
- ⏸️ NOT integrated into CI/CD pipeline (manual use only)
- ⏸️ NOT a blocker for commits/PRs

## Best Practices

1. **Run periodically** during cleanup/refactoring sessions
2. **Review results carefully** - don't blindly delete everything
3. **Update whitelist** when you find legitimate false positives
4. **Consider context** - some "unused" code might be:
   - Public API not used internally
   - Framework hooks/callbacks
   - Code used via dynamic dispatch/reflection
   - Future-proofing for planned features

## Example Session

```bash
# 1. Run scan
$ make dead-code

# 2. Review results
# (No output = no dead code found at 80% confidence)

# 3. Lower threshold to find more
$ uv run vulture maid_runner/ tests/ --min-confidence 60

# 4. Investigate findings
# - Is this actually unused?
# - Can it be safely deleted?
# - Is it a false positive?

# 5. Take action
# - Delete dead code OR
# - Add to .vulture whitelist if false positive

# 6. Re-run to verify
$ make dead-code
```

## Tips

- **Start conservative**: Use high confidence (80-90%) to find obvious dead code
- **Lower gradually**: Reduce confidence to find more candidates, but expect false positives
- **Don't obsess**: Some "dead" code might be worth keeping (public API, documentation examples)
- **Use with MAID**: Cross-reference with manifests - if it's not declared and not used, delete it!

## MAID-Specific Use Case

Vulture is particularly useful for finding:

1. **Private functions declared in manifests but never tested**
   - These fail behavioral validation with the recent loophole fix
   - Vulture can help identify which ones are truly unused

2. **Implementation details not in manifests**
   - If vulture says it's unused AND it's not in a manifest, delete it
   - If vulture says it's unused BUT it's in a manifest, investigate why

3. **Stale refactoring artifacts**
   - After refactoring, old helper functions might be forgotten
   - Vulture finds them for cleanup
