- Tests are using pytest (primary) with unittest as fallback. Use pytest fixtures, parametrization, and plugins for enhanced testing capabilities.

# Rules for Effective Unit Testing in Python

1. **Test behavior, not implementation details**

   - Focus on the observable inputs and outputs of the system under test (SUT)
   - Do not test private methods directly; test them through public interfaces
   - Tests should remain valid even if internal implementation changes

2. **Minimize mocking to essential dependencies**

   - Only mock external systems you don't control (databases, APIs, file systems)
   - Use real implementations of your own dependencies when possible
   - If using a mock, it should represent realistic behavior of the real component
   - Use `unittest.mock` or `pytest-mock` for mocking needs

3. **Create test doubles that accurately reflect real behavior**

   - Stubs/mocks should follow the same contract as real implementations
   - Test both happy paths and edge cases/error conditions
   - Verify interactions with dependencies only when the interaction itself is the behavior being tested
   - Use `Mock`, `MagicMock`, or `patch` appropriately

4. **Use test fixtures intelligently**

   - Leverage pytest fixtures for setup and teardown
   - Set up controlled test environments rather than extensive mocking
   - For filesystem operations, use `tempfile` or `pytest-tmp-path`
   - For databases, use in-memory databases, transactions, or test containers
   - Use fixture scopes (function, class, module, session) appropriately

5. **Test at the appropriate level**

   - Unit tests: Test a single unit in isolation
   - Integration tests: Test how components work together
   - Clear distinction between unit and integration tests in organization
   - Use pytest markers to categorize tests (`@pytest.mark.unit`, `@pytest.mark.integration`)

6. **Make tests deterministic and independent**

   - Tests should not depend on each other
   - Tests should be repeatable with the same results
   - Avoid time-dependent tests; use `freezegun` for time mocking when necessary
   - Use `pytest-randomly` to ensure test independence

7. **Write tests before fixing bugs**

   - Create a test that reproduces the bug
   - Fix the bug
   - Verify the test passes

8. **Test for failure conditions**

   - Verify error handling works correctly using `pytest.raises()`
   - Test boundary conditions and edge cases
   - Don't only test the "happy path"
   - Test exception types and messages when relevant

9. **Keep tests simple and readable**

   - Use descriptive test names that explain what's being tested and expected results
   - Follow the AAA pattern: Arrange, Act, Assert
   - One logical assertion per test (may include multiple related technical assertions)
   - Use pytest's assert statements rather than unittest's assertX methods

10. **Tests should be maintainable**

    - DRY principle applies to test code, but clarity is more important
    - Tests should not be brittle (failing due to minor, unrelated changes)
    - Tests should run quickly to encourage frequent running
    - Use pytest parametrization for testing multiple input combinations

11. **Measure test quality, not just coverage**

    - Use `pytest-cov` for coverage reporting
    - Consider mutation testing with `mutmut` to verify tests catch actual bugs
    - Review tests as carefully as production code
    - Ensure failing a test provides clear indication of what's wrong

12. **Don't mock what you don't own**

    - Create adapters around external dependencies instead of mocking them directly
    - Mock your adapter interfaces, not third-party libraries
    - Use `responses` library for HTTP mocking instead of mocking requests directly

13. **Test state changes, not just function calls**

    - Verify the end state after operations, not just that methods were called
    - Check actual data changes rather than implementation details
    - Use `assert_called_with()` sparingly and only when the call itself is the behavior

14. **Make tests obvious and transparent**

    - A test should clearly show what it's testing without hidden complexity
    - Someone not familiar with the code should understand what a test verifies
    - Use clear variable names and avoid complex test helpers when possible

15. **Document test scenarios clearly**

    - Tests should serve as documentation for how components should behave
    - Use descriptive test names and docstrings to explain what's being tested and why
    - Use pytest's `-v` flag to see descriptive test names during execution

16. **Python-specific testing best practices**

    - Use `pytest.fixture` for reusable test setup
    - Leverage `pytest.mark.parametrize` for data-driven tests
    - Use `pytest.mark.skip` and `pytest.mark.skipif` for conditional test execution
    - Organize tests in a `tests/` directory mirroring your source structure
    - Use `conftest.py` for shared fixtures and configuration
    - Consider `factory_boy` for creating test data objects
    - Use `pytest-django` for Django-specific testing features when applicable

These rules should help guide the creation of tests that truly verify your Python code's behavior rather than just creating an illusion of test coverage.
