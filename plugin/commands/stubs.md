---
description: Generate failing test stubs from a manifest to kickstart TDD workflow
---

# MAID Generate Stubs Command

Generate failing test stubs from an existing manifest.

## Purpose

Automatically creates test file skeleton based on manifest's `expectedArtifacts`:
- Generates imports for all declared artifacts
- Creates test functions for each artifact
- Adds failing assertions (TDD red phase)
- Saves time writing boilerplate test code

## Usage

```bash
# Generate stubs from manifest
uv run maid generate-stubs $ARGUMENTS

# Example with specific manifest
uv run maid generate-stubs manifests/task-042-add-payment.manifest.json
```

## What Gets Generated

For a manifest with these artifacts:
```json
{
  "expectedArtifacts": {
    "file": "src/payments.py",
    "contains": [
      {"type": "function", "name": "process_payment"},
      {"type": "class", "name": "PaymentProcessor"},
      {"type": "function", "name": "validate_card", "class": "PaymentProcessor"}
    ]
  }
}
```

Generates test stubs like:
```python
import pytest
from src.payments import process_payment, PaymentProcessor


def test_process_payment_exists():
    """Test that process_payment function exists and is callable."""
    assert callable(process_payment)
    # TODO: Add real test assertions


def test_payment_processor_exists():
    """Test that PaymentProcessor class exists."""
    assert PaymentProcessor is not None
    # TODO: Add instantiation and method tests


def test_payment_processor_validate_card_exists():
    """Test that PaymentProcessor.validate_card method exists."""
    processor = PaymentProcessor()
    assert callable(processor.validate_card)
    # TODO: Add real test assertions
```

## TDD Workflow

1. **Create manifest**: `maid manifest create <file> --goal "..." --artifacts '[...]'`
2. **Generate stubs**: `maid generate-stubs <manifest>`
3. **Enhance tests**: Add real assertions and test cases
4. **Validate behavioral**: `maid validate <manifest> --validation-mode behavioral`
5. **Run tests (should fail)**: `maid test --manifest <manifest>`
6. **Implement code**: Make tests pass
7. **Validate implementation**: `maid validate <manifest> --validation-mode implementation`

## Example Usage

User: `/maid-runner:stubs manifests/task-042-add-payment.manifest.json`

1. Run `maid generate-stubs`
2. Show generated test file path
3. Show count of generated test functions
4. Explain next steps:
   - Enhance tests with real assertions
   - Tests should use all declared artifacts
   - Run behavioral validation to verify

## Output

After generating stubs:
- Path to generated test file
- Number of test functions created
- List of artifacts covered
- Next steps:
  - "Enhance tests in: tests/test_task_042_payment.py"
  - "Add assertions that USE the declared artifacts"
  - "Validate with: `maid validate <manifest> --validation-mode behavioral`"

## Notes

- Overwrites existing test file (use with care)
- Creates basic skeleton - you must add real test logic
- Tests generated in "failing" state (TDD red phase)
- Imports are auto-generated from manifest
- Test file path from manifest's `validationCommand`
