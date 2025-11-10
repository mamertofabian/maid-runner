---
description: Implement code to satisfy manifest requirements and pass tests
argument-hint: [manifest-file-path]
allowed-tools: Write, Edit, Read, Bash(pytest*), TodoWrite
---

## Task: Implement Code According to Manifest

Implement the code that satisfies the requirements in manifest: $1

### Process:

1. **Read the manifest** to understand:
   - The goal of the implementation
   - Which files can be created or edited
   - The expected artifacts (classes, functions, attributes)
   - The validation command to run tests

2. **Read the test files** specified in `readonlyFiles` to understand:
   - How the code will be used
   - What behavior is expected
   - Edge cases and error handling

3. **Implement the solution**:
   - Create new files as specified in `creatableFiles`
   - Edit existing files as specified in `editableFiles`
   - Ensure all expected artifacts are implemented:
     * Classes with correct base classes
     * Functions with correct parameter signatures
     * Attributes on the appropriate classes
   - Follow the existing code style and conventions

4. **Validate the implementation**:
   - Run the validation command from the manifest
   - Ensure ALL tests pass
   - Use AST validator to verify manifest alignment

### Implementation Checklist:

- [ ] All classes exist with correct inheritance
- [ ] All functions exist with correct parameters
- [ ] All attributes are accessible on their parent classes
- [ ] Code follows project conventions
- [ ] All tests in the test file(s) pass
- [ ] No unnecessary code or features added

### Important:

- Only implement what is EXPLICITLY required by the manifest
- Do not add extra features or "nice-to-haves"
- Focus on making the tests pass
- Maintain clean, readable code
- Use the TodoWrite tool to track your implementation progress

Run the validation command after implementation to ensure everything works correctly.