# MAID Runner v2 - Public API

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [04-core-manifest.md](04-core-manifest.md), [05-core-validation.md](05-core-validation.md)

## Purpose

The public API is the primary interface for all consumers: ecosystem tools (maid-lsp, maid-runner-mcp, maid-agents), CI/CD integrations, and custom scripts. It replaces the current subprocess-based integration pattern.

## Module Location

`maid_runner/__init__.py` - All public symbols are re-exported here.

## Top-Level Exports

```python
# maid_runner/__init__.py

"""MAID Runner - Manifest-driven AI Development validator.

Library API for validating code artifacts against manifest specifications.

Quick start:
    from maid_runner import validate, validate_all

    # Validate a single manifest
    result = validate("manifests/add-auth.manifest.yaml")
    print(result.success)  # True/False

    # Validate all manifests in a directory
    batch = validate_all("manifests/")
    print(f"{batch.passed}/{batch.total_manifests} passed")
"""

# Version
from maid_runner.__version__ import __version__

# Core convenience functions (most common usage)
from maid_runner.core.validate import validate, validate_all

# Core classes (for advanced usage)
from maid_runner.core.validate import ValidationEngine
from maid_runner.core.manifest import load_manifest, save_manifest
from maid_runner.core.chain import ManifestChain
from maid_runner.core.snapshot import generate_snapshot

# Types (for type annotations and matching)
from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    ArgSpec,
    FileSpec,
    FileMode,
    DeleteSpec,
    Manifest,
    TaskType,
    ValidationMode,
)

# Result types (for inspecting validation output)
from maid_runner.core.result import (
    ValidationResult,
    BatchValidationResult,
    ValidationError,
    ErrorCode,
    Severity,
    Location,
    FileTrackingReport,
    FileTrackingStatus,
    FileTrackingEntry,
    TestRunResult,
    BatchTestResult,
)

# Validator extension point
from maid_runner.validators import ValidatorRegistry, UnsupportedLanguageError
from maid_runner.validators.base import BaseValidator, FoundArtifact, CollectionResult

# Exceptions
from maid_runner.core.manifest import ManifestLoadError, ManifestSchemaError

# Public API declaration for tools
__all__ = [
    # Version
    "__version__",
    # Convenience functions
    "validate",
    "validate_all",
    # Core classes
    "ValidationEngine",
    "load_manifest",
    "save_manifest",
    "ManifestChain",
    "generate_snapshot",
    # Types
    "ArtifactKind",
    "ArtifactSpec",
    "ArgSpec",
    "FileSpec",
    "FileMode",
    "DeleteSpec",
    "Manifest",
    "TaskType",
    "ValidationMode",
    # Results
    "ValidationResult",
    "BatchValidationResult",
    "ValidationError",
    "ErrorCode",
    "Severity",
    "Location",
    "FileTrackingReport",
    "FileTrackingStatus",
    "FileTrackingEntry",
    "TestRunResult",
    "BatchTestResult",
    # Validators
    "ValidatorRegistry",
    "UnsupportedLanguageError",
    "BaseValidator",
    "FoundArtifact",
    "CollectionResult",
    # Exceptions
    "ManifestLoadError",
    "ManifestSchemaError",
]
```

## Usage Examples

### Basic Validation

```python
from maid_runner import validate

# Validate a single manifest (most common usage)
result = validate("manifests/add-auth.manifest.yaml")

if result.success:
    print("All checks passed")
else:
    for error in result.errors:
        print(f"{error.code.value}: {error.message}")
```

### Batch Validation

```python
from maid_runner import validate_all

# Validate all manifests in directory
batch = validate_all("manifests/")

print(f"Results: {batch.passed}/{batch.total_manifests} passed")
print(f"Skipped: {batch.skipped} (superseded)")

for result in batch.results:
    if not result.success:
        print(f"\n  FAIL: {result.manifest_slug}")
        for err in result.errors:
            print(f"    {err.code.value}: {err.message}")
```

### Behavioral Validation

```python
from maid_runner import validate, ValidationMode

# Check that tests USE the declared artifacts
result = validate(
    "manifests/add-auth.manifest.yaml",
    mode=ValidationMode.BEHAVIORAL,
)
```

### Manifest Chain Operations

```python
from maid_runner import ManifestChain

chain = ManifestChain("manifests/")

# List active manifests
for m in chain.active_manifests():
    print(f"{m.slug}: {m.goal}")

# Get merged artifacts for a file
artifacts = chain.merged_artifacts_for("src/auth/service.py")
for a in artifacts:
    print(f"  {a.kind.value}: {a.qualified_name}")

# Check supersession
if chain.is_superseded("old-manifest"):
    print(f"Superseded by: {chain.superseded_by('old-manifest')}")
```

### Loading Manifests

```python
from maid_runner import load_manifest, save_manifest

# Load any format (YAML v2 or JSON v1)
manifest = load_manifest("manifests/add-auth.manifest.yaml")
print(manifest.goal)
print(manifest.all_writable_paths)

# Save in v2 YAML format
save_manifest(manifest, "manifests/copy.manifest.yaml")
```

### Snapshot Generation

```python
from maid_runner import generate_snapshot

# Generate manifest from existing code
manifest = generate_snapshot("src/auth/service.py")
print(f"Found {len(manifest.all_file_specs[0].artifacts)} artifacts")
save_manifest(manifest, "manifests/snapshot-auth-service.manifest.yaml")
```

### Custom Validator Registration

```python
from maid_runner import ValidatorRegistry, BaseValidator, CollectionResult

class GoValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls):
        return (".go",)

    def collect_implementation_artifacts(self, source, file_path):
        # Custom Go parsing logic
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

# Register for .go files
ValidatorRegistry.register(GoValidator)
```

### Knowledge Graph (Optional)

```python
from maid_runner import ManifestChain
from maid_runner.graph import GraphBuilder, GraphQuery, export_dot

chain = ManifestChain("manifests/")
graph = GraphBuilder().build(chain)
query = GraphQuery(graph)

# Impact analysis
impact = query.impact_analysis("AuthService")
print(f"Changing AuthService affects {len(impact['transitive_impact'])} nodes")

# Export for visualization
with open("graph.dot", "w") as f:
    f.write(export_dot(graph))
```

### Coherence Validation (Optional)

```python
from maid_runner import ManifestChain
from maid_runner.coherence import CoherenceEngine

chain = ManifestChain("manifests/")
engine = CoherenceEngine()
result = engine.validate(chain)

if not result.success:
    for issue in result.issues:
        print(f"[{issue.severity.value}] {issue.issue_type.value}: {issue.message}")
```

### JSON Output

```python
from maid_runner import validate
import json

result = validate("manifests/add-auth.manifest.yaml")

# Structured JSON output (for tool integration)
print(result.to_json())

# Or as dict
data = result.to_dict()
```

## Ecosystem Integration Examples

### maid-lsp Integration

```python
# Before (v1): subprocess wrapping
import subprocess
result = subprocess.run(["maid", "validate", path, "--json"], capture_output=True)
data = json.loads(result.stdout)

# After (v2): direct library import
from maid_runner import validate, ValidationMode

result = validate(path, mode=ValidationMode.IMPLEMENTATION)
# Use result.errors directly - no stdout parsing needed
for error in result.errors:
    diagnostic = {
        "range": {"start": {"line": error.location.line, "character": error.location.column}},
        "severity": 1 if error.severity == Severity.ERROR else 2,
        "message": error.message,
        "code": error.code.value,
        "source": "maid-runner",
    }
```

### maid-runner-mcp Integration

```python
# Before (v1): subprocess wrapping
@mcp_tool
def maid_validate(path: str):
    result = subprocess.run(["maid", "validate", path, "--json"], capture_output=True)
    return json.loads(result.stdout)

# After (v2): direct library import
from maid_runner import validate

@mcp_tool
def maid_validate(path: str):
    result = validate(path)
    return result.to_dict()
```

### maid-agents Integration

```python
# Before (v1): subprocess wrapping
def run_validation(manifest_path):
    proc = subprocess.run(["maid", "validate", manifest_path], capture_output=True)
    return proc.returncode == 0

# After (v2): direct library import
from maid_runner import validate

def run_validation(manifest_path):
    result = validate(manifest_path)
    return result.success
```

## Stability Guarantees

### Public API (Stable)
Everything exported from `maid_runner.__init__` follows semantic versioning:
- Patch versions (2.0.x): Bug fixes only, no API changes
- Minor versions (2.x.0): Additive changes (new functions/fields), no breaking changes
- Major versions (x.0.0): Breaking changes allowed

### Internal API (Unstable)
Anything not in `__all__` or prefixed with `_` is internal and may change without notice:
- `maid_runner.core._type_compare`
- `maid_runner.core._file_discovery`
- Private methods on public classes
- Internal module organization within packages

### Extension Points (Stable)
- `BaseValidator` ABC - stable interface for custom validators
- `ValidatorRegistry` - stable registration API
- `BaseCheck` ABC (coherence) - stable interface for custom checks

## Error Handling Contract

All public functions follow these rules:

1. **`validate()` and `validate_all()` never raise on validation failures.** They return `ValidationResult` with `success=False` and populated `errors`.

2. **Manifest loading raises on I/O or parse errors.** `ManifestLoadError` for file issues, `ManifestSchemaError` for invalid manifest content.

3. **Missing validators raise `UnsupportedLanguageError`.** When a manifest references a file type without an installed validator.

4. **Type errors raise `TypeError` or `ValueError`.** When called with wrong argument types.

5. **Everything else is an internal bug.** Unexpected exceptions should be reported as issues.
