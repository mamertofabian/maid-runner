---
description: Validate a manifest against schema and implementation using AST validator
argument-hint: [manifest-file-path] [--chain]
allowed-tools: Read, Bash(uv run python -m pytest*), Bash(uv run python -m*)
---

## Task: Validate Manifest Against Schema and Implementation

Validate the manifest at: $ARGUMENTS

### Validation Steps:

1. **Schema Validation:**
   - Verify the manifest conforms to the JSON schema
   - Check all required fields are present
   - Validate field types and structure

2. **Implementation Validation (AST):**
   - Parse the implementation file specified in the manifest
   - Verify all expected artifacts exist:
     * Classes with correct base classes
     * Functions with correct parameters
     * Attributes on correct parent classes
   - Use AST validator for precise validation

3. **Manifest Chain Support:**
   - If `--chain` flag is provided, use manifest chaining
   - This validates against cumulative state from all manifests that touched the file
   - Useful for files modified by multiple tasks

### Validation Script:

Create and run a validation script:

```python
import json
import sys
from pathlib import Path
from validators.manifest_validator import validate_schema, validate_with_ast

def validate_manifest(manifest_path, use_chain=False):
    """Validate a manifest against schema and implementation."""
    manifest_path = Path(manifest_path)
    schema_path = Path("validators/schemas/manifest.schema.json")

    if not manifest_path.exists():
        print(f"❌ Manifest not found: {manifest_path}")
        return False

    if not schema_path.exists():
        print(f"❌ Schema not found: {schema_path}")
        return False

    try:
        # Load manifest
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Step 1: Validate against schema
        print(f"📋 Validating manifest against schema...")
        validate_schema(manifest_data, str(schema_path))
        print(f"✅ Schema validation passed")

        # Step 2: Validate implementation with AST
        implementation_file = manifest_data.get("expectedArtifacts", {}).get("file")
        if implementation_file:
            print(f"🔍 Validating implementation: {implementation_file}")

            if not Path(implementation_file).exists():
                print(f"❌ Implementation file not found: {implementation_file}")
                return False

            # Check if we should use manifest chaining
            if use_chain:
                print(f"🔗 Using manifest chain for cumulative validation")
                validate_with_ast(manifest_data, implementation_file, use_manifest_chain=True)
            else:
                validate_with_ast(manifest_data, implementation_file)

            print(f"✅ AST validation passed")

        # Step 3: Run validation command if specified
        validation_cmd = manifest_data.get("validationCommand")
        if validation_cmd:
            print(f"🧪 Running validation command: {validation_cmd}")
            import subprocess
            result = subprocess.run(
                f"uv run python -m {validation_cmd}",
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"✅ Tests passed")
            else:
                print(f"❌ Tests failed:")
                print(result.stdout)
                print(result.stderr)
                return False

        print(f"\n✨ All validations passed for {manifest_path.name}")
        return True

    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in manifest: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False

# Parse arguments
args = "$ARGUMENTS".split()
manifest_file = args[0] if args else ""
use_chain = "--chain" in args

if not manifest_file:
    print("❌ Please provide a manifest file path")
    sys.exit(1)

# Run validation
success = validate_manifest(manifest_file, use_chain)
sys.exit(0 if success else 1)
```

### Usage Examples:

```bash
# Basic validation
/validate-manifest manifests/task-001.manifest.json

# With manifest chaining (for cumulative validation)
/validate-manifest manifests/task-002.manifest.json --chain

# Validate all manifests
/validate-manifest manifests/*.json
```

### Output:

The command will show:
- ✅ Successful validations
- ❌ Failed validations with specific errors
- 📋 Schema validation status
- 🔍 AST validation details
- 🧪 Test execution results

### Integration with Workflow:

Use this command to:
1. Verify manifests before implementation
2. Check implementation compliance after coding
3. Validate refactoring didn't break the contract
4. Ensure manifest chain integrity for multi-task files

This command is essential for maintaining alignment between specifications, implementations, and tests in the MAID methodology!