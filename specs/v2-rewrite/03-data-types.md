# MAID Runner v2 - Data Types

**References:** [00-overview.md](00-overview.md), [02-manifest-schema-v2.md](02-manifest-schema-v2.md)

## Module Location

All shared data types live in `maid_runner/core/types.py` unless they belong to a specific subsystem (graph, coherence). Result types live in `maid_runner/core/result.py`.

## Core Types (`maid_runner/core/types.py`)

### ArtifactKind (Enum)

```python
from enum import Enum

class ArtifactKind(str, Enum):
    """The kind of code artifact declared in a manifest."""
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ATTRIBUTE = "attribute"
    INTERFACE = "interface"       # TypeScript
    TYPE = "type"                 # TypeScript type alias
    ENUM = "enum"
    NAMESPACE = "namespace"       # TypeScript
```

### TaskType (Enum)

```python
class TaskType(str, Enum):
    """The type of task a manifest represents."""
    FEATURE = "feature"
    FIX = "fix"
    REFACTOR = "refactor"
    SNAPSHOT = "snapshot"
    SYSTEM_SNAPSHOT = "system-snapshot"
```

### ValidationMode (Enum)

```python
class ValidationMode(str, Enum):
    """Which validation pass to run."""
    BEHAVIORAL = "behavioral"         # Check tests USE declared artifacts
    IMPLEMENTATION = "implementation"  # Check code DEFINES declared artifacts
```

### FileMode (Enum)

```python
class FileMode(str, Enum):
    """How a file is tracked in a manifest."""
    CREATE = "create"      # Strict validation (exact match)
    EDIT = "edit"          # Permissive validation (contains at least)
    READ = "read"          # Read-only dependency
    DELETE = "delete"      # File should be absent
    SNAPSHOT = "snapshot"  # Strict validation (snapshot mode)
```

### ArgSpec (Dataclass)

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ArgSpec:
    """A function/method argument specification."""
    name: str
    type: Optional[str] = None
    default: Optional[str] = None
```

### ArtifactSpec (Dataclass)

```python
@dataclass(frozen=True)
class ArtifactSpec:
    """A single code artifact declared in a manifest."""
    kind: ArtifactKind
    name: str
    description: Optional[str] = None

    # Function/method fields
    args: tuple[ArgSpec, ...] = ()
    returns: Optional[str] = None
    raises: tuple[str, ...] = ()
    is_async: bool = False

    # Class fields
    bases: tuple[str, ...] = ()

    # Method/attribute fields (parent class)
    of: Optional[str] = None

    # Attribute fields
    type_annotation: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        """Full name including parent class, e.g. 'AuthService.login'."""
        if self.of:
            return f"{self.of}.{self.name}"
        return self.name

    @property
    def is_private(self) -> bool:
        """Whether this is a private artifact (name starts with _)."""
        return self.name.startswith("_")

    def merge_key(self) -> str:
        """Key used for deduplication when merging manifest chains.
        Methods are keyed by class.method, functions by name alone.
        """
        if self.kind == ArtifactKind.METHOD and self.of:
            return f"{self.of}.{self.name}"
        if self.kind == ArtifactKind.ATTRIBUTE and self.of:
            return f"{self.of}.{self.name}"
        return self.name
```

### FileSpec (Dataclass)

```python
@dataclass(frozen=True)
class FileSpec:
    """A file and its expected artifacts in a manifest."""
    path: str
    artifacts: tuple[ArtifactSpec, ...]
    status: str = "present"  # "present" | "absent"
    mode: FileMode = FileMode.CREATE  # Set during manifest loading based on section

    @property
    def is_strict(self) -> bool:
        """Whether this file uses strict validation (exact match)."""
        return self.mode in (FileMode.CREATE, FileMode.SNAPSHOT)

    @property
    def is_absent(self) -> bool:
        """Whether this file should NOT exist."""
        return self.status == "absent" or self.mode == FileMode.DELETE
```

### DeleteSpec (Dataclass)

```python
@dataclass(frozen=True)
class DeleteSpec:
    """A file to be deleted."""
    path: str
    reason: Optional[str] = None
```

### Manifest (Dataclass)

```python
@dataclass(frozen=True)
class Manifest:
    """A parsed and validated manifest.

    This is the canonical internal representation, regardless of
    whether the source was YAML v2 or JSON v1.
    """
    # Identity
    slug: str                              # Derived from filename (e.g. "add-jwt-auth")
    source_path: str                       # Absolute path to the manifest file

    # Required fields
    goal: str
    validate_commands: tuple[tuple[str, ...], ...]  # Commands as tuples of strings

    # File specifications (grouped by mode)
    files_create: tuple[FileSpec, ...] = ()
    files_edit: tuple[FileSpec, ...] = ()
    files_read: tuple[str, ...] = ()
    files_delete: tuple[DeleteSpec, ...] = ()
    files_snapshot: tuple[FileSpec, ...] = ()

    # Optional fields
    schema_version: str = "2"
    task_type: Optional[TaskType] = None
    description: Optional[str] = None
    supersedes: tuple[str, ...] = ()       # Slugs of superseded manifests
    created: Optional[str] = None          # ISO 8601 timestamp
    metadata: Optional[dict] = None

    @property
    def all_file_specs(self) -> list[FileSpec]:
        """All FileSpec objects across create, edit, and snapshot sections."""
        return list(self.files_create) + list(self.files_edit) + list(self.files_snapshot)

    @property
    def all_writable_paths(self) -> set[str]:
        """All file paths this manifest declares as writable."""
        paths = {fs.path for fs in self.files_create}
        paths |= {fs.path for fs in self.files_edit}
        paths |= {ds.path for ds in self.files_delete}
        paths |= {fs.path for fs in self.files_snapshot}
        return paths

    @property
    def all_referenced_paths(self) -> set[str]:
        """All file paths referenced by this manifest (writable + read-only)."""
        return self.all_writable_paths | set(self.files_read)

    @property
    def is_superseded_by(self) -> bool:
        """Whether another manifest supersedes this one.
        This is set externally by ManifestChain during resolution.
        """
        # This is determined by the chain, not the manifest itself.
        # Manifests don't know if they've been superseded.
        raise NotImplementedError("Use ManifestChain.is_superseded()")

    def file_spec_for(self, path: str) -> Optional[FileSpec]:
        """Find the FileSpec for a given file path, or None."""
        for fs in self.all_file_specs:
            if fs.path == path:
                return fs
        return None

    def artifacts_for(self, path: str) -> tuple[ArtifactSpec, ...]:
        """Get all artifacts declared for a specific file path."""
        fs = self.file_spec_for(path)
        return fs.artifacts if fs else ()
```

## Result Types (`maid_runner/core/result.py`)

### ErrorCode (Enum)

```python
class ErrorCode(str, Enum):
    """Standardized error codes for validation errors.

    Ranges:
    - E0xx: File/JSON/YAML errors
    - E1xx: Semantic errors
    - E2xx: Behavioral validation errors
    - E3xx: Implementation validation errors
    - E4xx: Coherence errors
    - E9xx: System errors
    """
    # File errors
    FILE_NOT_FOUND = "E001"
    FILE_READ_ERROR = "E002"
    MANIFEST_PARSE_ERROR = "E003"
    SCHEMA_VALIDATION_ERROR = "E004"

    # Semantic errors
    DUPLICATE_FILE = "E100"
    FILE_IN_MULTIPLE_SECTIONS = "E101"
    SUPERSEDED_MANIFEST_NOT_FOUND = "E102"
    CIRCULAR_SUPERSESSION = "E103"
    EMPTY_ARTIFACTS = "E104"
    INVALID_TASK_TYPE = "E105"

    # Behavioral validation errors
    ARTIFACT_NOT_USED_IN_TESTS = "E200"
    TEST_FILE_NOT_FOUND = "E201"
    TEST_FILE_NOT_IN_READONLY = "E202"

    # Implementation validation errors
    ARTIFACT_NOT_DEFINED = "E300"
    UNEXPECTED_ARTIFACT = "E301"
    TYPE_MISMATCH = "E302"
    SIGNATURE_MISMATCH = "E303"
    MISSING_RETURN_TYPE = "E304"
    FILE_SHOULD_BE_ABSENT = "E305"
    FILE_SHOULD_BE_PRESENT = "E306"
    VALIDATOR_NOT_AVAILABLE = "E307"

    # Coherence errors
    COHERENCE_DUPLICATE = "E400"
    COHERENCE_SIGNATURE_CONFLICT = "E401"
    COHERENCE_BOUNDARY_VIOLATION = "E402"
    COHERENCE_NAMING_VIOLATION = "E403"
    COHERENCE_DEPENDENCY_MISSING = "E404"

    # System errors
    INTERNAL_ERROR = "E900"
    UNSUPPORTED_LANGUAGE = "E901"
```

### Severity (Enum)

```python
class Severity(str, Enum):
    """Severity level for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
```

### Location (Dataclass)

```python
@dataclass(frozen=True)
class Location:
    """Source location of a validation issue."""
    file: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
```

### ValidationError (Dataclass)

```python
@dataclass(frozen=True)
class ValidationError:
    """A single validation error or warning."""
    code: ErrorCode
    message: str
    severity: Severity = Severity.ERROR
    location: Optional[Location] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        d = {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.location:
            d["location"] = {
                "file": self.location.file,
                "line": self.location.line,
                "column": self.location.column,
            }
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d
```

### FileTrackingStatus (Enum)

```python
class FileTrackingStatus(str, Enum):
    """Tracking status of a file in the MAID system."""
    UNDECLARED = "undeclared"     # File exists but not in any manifest
    REGISTERED = "registered"    # In manifest but incomplete compliance
    TRACKED = "tracked"          # Full MAID compliance
```

### FileTrackingEntry (Dataclass)

```python
@dataclass(frozen=True)
class FileTrackingEntry:
    """Tracking status for a single file."""
    path: str
    status: FileTrackingStatus
    manifests: tuple[str, ...] = ()   # Manifest slugs that reference this file
    issues: tuple[str, ...] = ()      # Description of compliance issues
```

### FileTrackingReport (Dataclass)

```python
@dataclass(frozen=True)
class FileTrackingReport:
    """Complete file tracking analysis for a project."""
    entries: tuple[FileTrackingEntry, ...]

    @property
    def undeclared(self) -> list[FileTrackingEntry]:
        return [e for e in self.entries if e.status == FileTrackingStatus.UNDECLARED]

    @property
    def registered(self) -> list[FileTrackingEntry]:
        return [e for e in self.entries if e.status == FileTrackingStatus.REGISTERED]

    @property
    def tracked(self) -> list[FileTrackingEntry]:
        return [e for e in self.entries if e.status == FileTrackingStatus.TRACKED]
```

### ValidationResult (Dataclass)

```python
@dataclass
class ValidationResult:
    """Complete result of a validation run."""
    success: bool
    manifest_slug: str
    manifest_path: str
    mode: ValidationMode
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    file_tracking: Optional[FileTrackingReport] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON output."""
        d = {
            "success": self.success,
            "manifest": self.manifest_slug,
            "manifest_path": self.manifest_path,
            "mode": self.mode.value,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }
        if self.file_tracking:
            d["file_tracking"] = {
                "undeclared": [e.path for e in self.file_tracking.undeclared],
                "registered": [e.path for e in self.file_tracking.registered],
                "tracked": [e.path for e in self.file_tracking.tracked],
            }
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d

    def to_json(self) -> str:
        """Serialize to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=2)
```

## Batch Result Types

### BatchValidationResult (Dataclass)

```python
@dataclass
class BatchValidationResult:
    """Result of validating all manifests in a directory."""
    results: list[ValidationResult]
    total_manifests: int
    passed: int
    failed: int
    skipped: int                     # Superseded manifests
    duration_ms: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "total": self.total_manifests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "duration_ms": self.duration_ms,
        }
```

### TestRunResult (Dataclass)

```python
@dataclass
class TestRunResult:
    """Result of running validation commands."""
    manifest_slug: str
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.exit_code == 0
```

### BatchTestResult (Dataclass)

```python
@dataclass
class BatchTestResult:
    """Result of running all validation commands."""
    results: list[TestRunResult]
    total: int
    passed: int
    failed: int
    duration_ms: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.failed == 0
```

## Validator Types (`maid_runner/validators/base.py`)

### FoundArtifact (Dataclass)

```python
@dataclass(frozen=True)
class FoundArtifact:
    """An artifact found by a language validator in source code.

    This is what validators return - the actual artifacts found by
    analyzing source code AST. Compare against ArtifactSpec to validate.
    """
    kind: ArtifactKind
    name: str
    of: Optional[str] = None           # Parent class (for methods/class attrs)
    args: tuple[ArgSpec, ...] = ()
    returns: Optional[str] = None
    is_async: bool = False
    bases: tuple[str, ...] = ()
    type_annotation: Optional[str] = None
    line: Optional[int] = None         # Source line number
    column: Optional[int] = None       # Source column

    @property
    def is_private(self) -> bool:
        return self.name.startswith("_")

    @property
    def qualified_name(self) -> str:
        if self.of:
            return f"{self.of}.{self.name}"
        return self.name

    def merge_key(self) -> str:
        """Same merge key logic as ArtifactSpec for comparison."""
        if self.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and self.of:
            return f"{self.of}.{self.name}"
        return self.name
```

### CollectionResult (Dataclass)

```python
@dataclass
class CollectionResult:
    """Result of collecting artifacts from a source file."""
    artifacts: list[FoundArtifact]
    language: str                       # "python", "typescript", "svelte"
    file_path: str
    errors: list[str] = field(default_factory=list)  # Parse errors
```

## Graph Types (`maid_runner/graph/model.py`)

See [07-graph-module.md](07-graph-module.md) for complete graph type definitions.

## Coherence Types (`maid_runner/coherence/result.py`)

See [08-coherence-module.md](08-coherence-module.md) for complete coherence type definitions.

## Type Design Principles

1. **Frozen dataclasses** for all value objects (Manifest, ArtifactSpec, FileSpec, etc.) - immutability prevents bugs
2. **Tuples over lists** in frozen dataclasses (lists aren't hashable)
3. **String enums** (`str, Enum`) for JSON serialization compatibility
4. **Optional fields default to None**, collection fields default to empty tuples
5. **No inheritance between data types** - composition over inheritance for data
6. **`to_dict()` method** on all types that need JSON serialization
7. **`merge_key()` method** on artifacts for chain merge deduplication
