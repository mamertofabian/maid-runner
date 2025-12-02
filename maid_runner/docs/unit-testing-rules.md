# Rules for Effective Unit Testing

## Testing Frameworks

| Language   | Primary Framework | Fallback/Alternative |
|------------|-------------------|----------------------|
| Python     | pytest            | unittest             |
| TypeScript | Vitest / Jest     | Mocha + Chai         |

Use the primary framework's fixtures, parametrization, and plugins for enhanced testing capabilities.

---

## Core Principles (Language-Agnostic)

### 1. Test behavior, not implementation details

- Focus on the observable inputs and outputs of the system under test (SUT)
- Do not test private methods directly; test them through public interfaces
- Tests should remain valid even if internal implementation changes

### 2. Minimize mocking to essential dependencies

- Only mock external systems you don't control (databases, APIs, file systems)
- Use real implementations of your own dependencies when possible
- If using a mock, it should represent realistic behavior of the real component

**Python:** Use `unittest.mock` or `pytest-mock`
**TypeScript:** Use `jest.mock()`, `vi.mock()` (Vitest), or `sinon`

### 3. Create test doubles that accurately reflect real behavior

- Stubs/mocks should follow the same contract as real implementations
- Test both happy paths and edge cases/error conditions
- Verify interactions with dependencies only when the interaction itself is the behavior being tested

**Python:** Use `Mock`, `MagicMock`, or `patch` appropriately
**TypeScript:** Use `jest.fn()`, `vi.fn()`, or typed mock factories

### 4. Use test fixtures intelligently

- Leverage framework-provided fixtures for setup and teardown
- Set up controlled test environments rather than extensive mocking
- For filesystem operations, use temporary directories
- For databases, use in-memory databases, transactions, or test containers

**Python:** pytest fixtures with scopes (function, class, module, session), `tempfile`, `pytest-tmp-path`
**TypeScript:** `beforeEach`/`afterEach`, `beforeAll`/`afterAll`, `tmp-promise` or `memfs`

### 5. Test at the appropriate level

- Unit tests: Test a single unit in isolation
- Integration tests: Test how components work together
- Clear distinction between unit and integration tests in organization

**Python:** Use pytest markers (`@pytest.mark.unit`, `@pytest.mark.integration`)
**TypeScript:** Use `describe.skip`, test file naming conventions, or Jest projects

### 6. Make tests deterministic and independent

- Tests should not depend on each other
- Tests should be repeatable with the same results
- Avoid time-dependent tests; use time mocking when necessary

**Python:** Use `freezegun` for time mocking, `pytest-randomly` to ensure independence
**TypeScript:** Use `jest.useFakeTimers()`, `vi.useFakeTimers()`, or `sinon.useFakeTimers()`

### 7. Write tests before fixing bugs

- Create a test that reproduces the bug
- Fix the bug
- Verify the test passes

### 8. Test for failure conditions

- Verify error handling works correctly
- Test boundary conditions and edge cases
- Don't only test the "happy path"
- Test exception/error types and messages when relevant

**Python:** Use `pytest.raises()` for exception testing
**TypeScript:** Use `expect(() => fn()).toThrow()` or `await expect(promise).rejects.toThrow()`

### 9. Keep tests simple and readable

- Use descriptive test names that explain what's being tested and expected results
- Follow the AAA pattern: Arrange, Act, Assert
- One logical assertion per test (may include multiple related technical assertions)

**Python:** Use pytest's `assert` statements rather than unittest's `assertX` methods
**TypeScript:** Use expressive matchers like `expect(x).toBe()`, `toEqual()`, `toContain()`

### 10. Tests should be maintainable

- DRY principle applies to test code, but clarity is more important
- Tests should not be brittle (failing due to minor, unrelated changes)
- Tests should run quickly to encourage frequent running
- Use parametrization for testing multiple input combinations

**Python:** Use `@pytest.mark.parametrize`
**TypeScript:** Use `test.each()` or `it.each()`

### 11. Measure test quality, not just coverage

- Use coverage reporting tools
- Consider mutation testing to verify tests catch actual bugs
- Review tests as carefully as production code
- Ensure failing a test provides clear indication of what's wrong

**Python:** `pytest-cov`, `mutmut`
**TypeScript:** Built-in coverage in Jest/Vitest (`--coverage`), `stryker-mutator`

### 12. Don't mock what you don't own

- Create adapters around external dependencies instead of mocking them directly
- Mock your adapter interfaces, not third-party libraries

**Python:** Use `responses` library for HTTP mocking
**TypeScript:** Use `msw` (Mock Service Worker) or `nock` for HTTP mocking

### 13. Test state changes, not just function calls

- Verify the end state after operations, not just that methods were called
- Check actual data changes rather than implementation details
- Use call verification sparingly and only when the call itself is the behavior

**Python:** Use `assert_called_with()` sparingly
**TypeScript:** Use `expect(mock).toHaveBeenCalledWith()` sparingly

### 14. Make tests obvious and transparent

- A test should clearly show what it's testing without hidden complexity
- Someone not familiar with the code should understand what a test verifies
- Use clear variable names and avoid complex test helpers when possible

### 15. Document test scenarios clearly

- Tests should serve as documentation for how components should behave
- Use descriptive test names and comments to explain what's being tested and why
- Use verbose test output to see descriptive test names during execution

**Python:** Use pytest's `-v` flag and docstrings
**TypeScript:** Use nested `describe` blocks and descriptive `it`/`test` names

---

## Language-Specific Best Practices

### Python

- Use `pytest.fixture` for reusable test setup
- Leverage `@pytest.mark.parametrize` for data-driven tests
- Use `@pytest.mark.skip` and `@pytest.mark.skipif` for conditional test execution
- Organize tests in a `tests/` directory mirroring your source structure
- Use `conftest.py` for shared fixtures and configuration
- Consider `factory_boy` for creating test data objects
- Use `pytest-django` for Django-specific testing features when applicable
- Use `pytest-asyncio` for async code testing

### TypeScript

- Use `describe` blocks to group related tests logically
- Leverage `test.each()` / `it.each()` for data-driven tests
- Use `test.skip()` and `test.todo()` for conditional/pending tests
- Organize tests in `__tests__/` directories or `.test.ts`/`.spec.ts` files alongside source
- Use setup files for shared configuration and global mocks
- Consider `faker` or `fishery` for creating test data objects
- Use `@testing-library/*` for React/DOM testing when applicable
- Use native async/await with proper `await expect()` patterns for async code
- Leverage TypeScript's type system in tests for better type safety
- Use `satisfies` or type assertions to ensure mock objects match interfaces

---

## Summary

These rules guide the creation of tests that truly verify your code's behavior rather than creating an illusion of test coverage. The core principles apply across languages—only the tooling differs.
