---
description: Generate tests based on a MAID manifest
argument-hint: [manifest-file-path]
allowed-tools: Write, Read, Glob
---

## Task: Generate Tests from Manifest

Generate comprehensive test files based on the manifest at: $1

### Requirements:

1. Read and analyze the manifest file
2. Generate test file(s) as specified in the manifest's `readonlyFiles`
3. The tests must:
   - Import the artifacts specified in `expectedArtifacts`
   - Test all functions with their expected parameters
   - Test all classes and their inheritance
   - Test attributes on their parent classes
   - Include both positive and negative test cases
   - Use pytest framework conventions

### Test Coverage Should Include:

1. **For Functions:**
   - Test the function exists and is callable
   - Test with valid parameters
   - Test parameter validation (if applicable)
   - Test return values

2. **For Classes:**
   - Test class instantiation
   - Test inheritance chain (if base class specified)
   - Test class methods and attributes
   - Test error handling

3. **For Attributes:**
   - Test attribute exists on instances
   - Test attribute getters/setters
   - Test attribute types and validation

### Example Test Structure:

```python
import pytest
from [module] import [artifacts]

def test_function_exists_with_correct_signature():
    """Test that function has expected parameters."""
    # Test implementation

def test_class_inheritance():
    """Test that class inherits from expected base."""
    # Test implementation

def test_attribute_access():
    """Test that attributes are accessible on class instances."""
    # Test implementation

def test_error_conditions():
    """Test that appropriate errors are raised."""
    # Test implementation
```

The tests should be thorough enough to validate the complete implementation as specified in the manifest.