---
description: Improve test coverage and update manifest accordingly
argument-hint: [test-file-path] [manifest-file-path]
allowed-tools: Edit, Read, Write, Bash(pytest*), Bash(coverage*)
---

## Task: Improve Tests and Update Manifest

Enhance the tests in $1 and update manifest: $2 to reflect any new requirements.

### Test Improvement Areas:

1. **Coverage Enhancement:**
   - Add edge case testing
   - Test error conditions and exceptions
   - Test boundary values
   - Add property-based testing where applicable
   - Test concurrent/async behavior if relevant

2. **Test Quality:**
   - Improve test names for clarity
   - Add comprehensive docstrings
   - Group related tests into classes
   - Use appropriate pytest fixtures
   - Add parametrized tests for similar cases
   - Reduce test duplication

3. **Assertions:**
   - Make assertions more specific
   - Test not just success but correct values
   - Verify side effects and state changes
   - Check error messages and types

4. **Performance Tests:**
   - Add timing constraints where relevant
   - Test with large datasets
   - Check memory usage for critical operations

### Process:

1. **Analyze Current Coverage:**
   ```bash
   uv run python -m pytest $1 --cov --cov-report=term-missing
   ```

2. **Identify Gaps:**
   - Untested code paths
   - Missing error scenarios
   - Uncovered edge cases
   - Missing integration tests

3. **Enhance Tests:**
   - Add new test cases
   - Improve existing tests
   - Add test fixtures and helpers
   - Use pytest features effectively

4. **Update Manifest if Needed:**
   - If tests reveal missing artifacts, add them to manifest
   - If new parameters are tested, update function signatures
   - If new classes/inheritance discovered, update manifest
   - Ensure manifest accurately reflects the tested contract

5. **Validate Alignment:**
   - Run AST validator to ensure manifest matches implementation
   - Verify all tests pass
   - Check coverage has improved

### Test Patterns to Consider:

```python
# Parametrized tests
@pytest.mark.parametrize("input,expected", [
    (val1, result1),
    (val2, result2),
])
def test_multiple_cases(input, expected):
    assert function(input) == expected

# Fixture usage
@pytest.fixture
def setup_data():
    return {"key": "value"}

# Testing exceptions
def test_raises_on_invalid_input():
    with pytest.raises(ValueError, match="Expected error"):
        function(invalid_input)

# Property-based testing (if hypothesis installed)
@given(integers())
def test_property(value):
    assert property_holds(value)
```

### Checklist:

- [ ] Coverage increased (aim for >90%)
- [ ] All edge cases tested
- [ ] Error conditions verified
- [ ] Tests are maintainable and clear
- [ ] Manifest updated to reflect complete API
- [ ] All tests pass
- [ ] AST validation passes

The goal is comprehensive, maintainable tests that fully specify the expected behavior!