---
description: Enhance test coverage and quality
argument-hint: [test-file-path]
---

Improve tests in: $1

Tasks:
1. Review existing tests - flag any without assertions (smoke tests)
2. Add edge cases and error scenarios
3. Ensure tests USE artifacts AND ASSERT on outputs/side effects
4. Use `capsys` for stdout, verify return values, check state changes
5. Validate: `maid validate` and `maid test`

**No smoke tests.** See `docs/unit-testing-rules.md`.
