# MAID Runner v2 - Core Validation Engine

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [04-core-manifest.md](04-core-manifest.md), [06-validators.md](06-validators.md)

## Module Location

`maid_runner/core/validate.py`

## Responsibilities

1. Orchestrate all validation passes (schema, behavioral, implementation)
2. Dispatch to language validators via plugin registry
3. Compare declared artifacts (ArtifactSpec) against found artifacts (FoundArtifact)
4. Enforce strict vs permissive modes
5. Run file tracking analysis
6. Aggregate results into ValidationResult

## Public API

```python
class ValidationEngine:
    """Orchestrates manifest validation.

    This is the main entry point for all validation. It coordinates
    between manifest loading, chain resolution, language validators,
    and result aggregation.
    """

    def __init__(self, project_root: str | Path = "."):
        """Initialize engine with project root for resolving file paths.

        Args:
            project_root: Root directory for resolving relative paths in manifests.
        """

    def validate(
        self,
        manifest: Manifest | str | Path,
        *,
        mode: ValidationMode = ValidationMode.IMPLEMENTATION,
        use_chain: bool = False,
        manifest_dir: str | Path = "manifests/",
    ) -> ValidationResult:
        """Validate a single manifest.

        Args:
            manifest: Manifest object, or path to manifest file.
            mode: Validation mode (behavioral or implementation).
            use_chain: Whether to merge with manifest chain for cumulative validation.
            manifest_dir: Directory for chain resolution (only used if use_chain=True).

        Returns:
            ValidationResult with errors, warnings, and file tracking info.
        """

    def validate_all(
        self,
        manifest_dir: str | Path = "manifests/",
        *,
        mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    ) -> BatchValidationResult:
        """Validate all active manifests in a directory.

        Automatically:
        - Discovers all manifests
        - Excludes superseded manifests
        - Uses manifest chain for cumulative validation
        - Aggregates results

        Args:
            manifest_dir: Directory containing manifests.
            mode: Validation mode.

        Returns:
            BatchValidationResult with per-manifest results.
        """

    def validate_behavioral(
        self,
        manifest: Manifest,
        chain: ManifestChain | None = None,
    ) -> list[ValidationError]:
        """Run behavioral validation only.

        Checks that test files USE the declared artifacts.
        Scans test files with AST analysis to find artifact references.

        Returns:
            List of validation errors (empty if all artifacts are used in tests).
        """

    def validate_implementation(
        self,
        manifest: Manifest,
        chain: ManifestChain | None = None,
    ) -> list[ValidationError]:
        """Run implementation validation only.

        Checks that source files DEFINE the declared artifacts.
        Uses language-specific validators to collect artifacts from code.

        Returns:
            List of validation errors.
        """

    def run_file_tracking(
        self,
        chain: ManifestChain,
    ) -> FileTrackingReport:
        """Analyze file tracking status across the project.

        Classifies every source file as UNDECLARED, REGISTERED, or TRACKED.

        Returns:
            FileTrackingReport with categorized files.
        """
```

### Convenience Functions (Module-Level)

```python
def validate(
    manifest_path: str | Path,
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    use_chain: bool = True,
    manifest_dir: str | Path = "manifests/",
    project_root: str | Path = ".",
) -> ValidationResult:
    """Convenience function: validate a single manifest.

    Creates a ValidationEngine and calls validate().
    This is the primary entry point for library users.
    """


def validate_all(
    manifest_dir: str | Path = "manifests/",
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    project_root: str | Path = ".",
) -> BatchValidationResult:
    """Convenience function: validate all manifests in a directory."""
```

## Validation Passes

### Pass 1: Schema Validation

**When:** Always runs first, regardless of mode.

**What it does:**
1. Load manifest file
2. Validate against JSON Schema (`manifest.v2.schema.json`)
3. If v1 format detected, convert via compat layer first
4. Check semantic constraints not expressible in JSON Schema:
   - At least one of files.create/edit/snapshot/delete must be non-empty
   - Artifact `of` field is present for methods and class attributes
   - No duplicate file paths across sections
   - File in `files.read` is not also in `files.create` or `files.edit`

**Errors produced:** E003, E004, E100, E101, E104, E105

### Pass 2: Behavioral Validation

**When:** `mode == ValidationMode.BEHAVIORAL`

**Purpose:** Verify that test files USE the declared artifacts. This ensures tests are actually testing what the manifest declares, not something else.

**Algorithm:**

```
For each FileSpec in manifest (create + edit + snapshot):
    For each ArtifactSpec in FileSpec.artifacts:
        Find test files:
            1. Check files.read for test files (pattern: test_*.py, *.test.ts, etc.)
            2. Extract test file paths from validate commands
        For each test file:
            Parse test file with appropriate language validator
            Collect all artifact REFERENCES (imports, calls, attribute access)
            Check if artifact.name appears in references
        If artifact not referenced in any test file:
            Error: E200 "Artifact '{name}' not used in any test file"
```

**What counts as "using" an artifact in a test:**
- Python: importing the name, calling the function/method, accessing the attribute
- TypeScript: importing the name, calling the function, referencing the type
- Svelte: importing/using the component

**Key behavior from v1 to preserve:**
- Behavioral validation only checks artifacts from the CURRENT manifest, not the merged chain
- Test files are identified by patterns (`test_*.py`, `*_test.py`, `*.test.ts`, `*.spec.ts`)
- Test files can also be extracted from `validate` commands

### Pass 3: Implementation Validation

**When:** `mode == ValidationMode.IMPLEMENTATION`

**Purpose:** Verify that source files DEFINE the declared artifacts with correct signatures.

**Algorithm:**

```
For each FileSpec in manifest (create + edit + snapshot):
    If FileSpec.is_absent:
        Verify file does NOT exist at path -> E305 if it does
        Continue to next FileSpec

    Verify file EXISTS at path -> E306 if missing

    Get language validator from registry (by file extension)
        -> E307 if no validator available (e.g., .go file without Go plugin)

    Collect artifacts from source code:
        result = validator.collect_implementation_artifacts(file_path)

    Get expected artifacts:
        If use_chain:
            expected = chain.merged_artifacts_for(file_path)
        Else:
            expected = file_spec.artifacts

    Compare expected vs found:
        For each expected artifact:
            Find matching found artifact (by merge_key)
            If not found:
                Error: E300 "Artifact '{name}' not defined in {path}"
            If found, validate details:
                Check type hints match (args, returns) -> E302
                Check signature match (arg names, count) -> E303
                Check return type annotation -> E304

        If FileSpec.is_strict:  # CREATE or SNAPSHOT mode
            For each found PUBLIC artifact NOT in expected:
                Error: E301 "Unexpected public artifact '{name}' in {path}"

        If FileSpec mode is EDIT (permissive):
            Additional public artifacts are allowed (no E301)
```

### Type Comparison

Type hints are compared with normalization to handle equivalent representations:

```python
def types_match(expected: str | None, found: str | None) -> bool:
    """Compare two type annotations with normalization.

    Normalizations applied:
    - Optional[X] == Union[X, None] == X | None
    - Union members sorted alphabetically
    - Whitespace stripped
    - Leading module prefixes stripped (typing.List -> List)
    - list[X] == List[X] (PEP 585 equivalence)
    - dict[K,V] == Dict[K,V]
    - tuple[X,...] == Tuple[X,...]

    If expected is None, any found type is acceptable.
    If found is None but expected is not None, it's a warning (not error).
    """
```

This logic is ported from the current `_type_normalization.py` and `_type_validation.py` modules. It lives in a private helper `maid_runner/core/_type_compare.py`.

### File Tracking Analysis

**When:** After implementation validation, when `use_chain=True`.

**Purpose:** Classify all source files in the project by their MAID tracking status.

**Algorithm:**

```
1. Discover all source files in project (Python, TypeScript, Svelte, etc.)
   - Exclude: node_modules/, .venv/, __pycache__/, .git/, etc.
   - Exclude: test files, manifest files, config files

2. Get all tracked paths from chain: chain.all_tracked_paths()

3. For each source file:
   If path not in any manifest:
       Status = UNDECLARED
   Else if path in manifest but:
       - No expectedArtifacts for this file, OR
       - No validation command covering this file, OR
       - Only appears in files.read
       Status = REGISTERED (with specific issues listed)
   Else:
       Status = TRACKED

4. Build FileTrackingReport
```

### Absent Status Validation

For files/artifacts marked as absent (deletion tracking):

```
If file_spec.status == "absent" or file_spec.mode == DELETE:
    If file EXISTS on disk:
        Error: E305 "File '{path}' should be absent but still exists"
    If file does NOT exist:
        Pass (expected state)

    Also check:
    - No other active manifest still references this file as create/edit
    - No test files still import from this file
```

## Internal Architecture

```
validate.py
├── ValidationEngine              # Main orchestration class
│   ├── validate()                # Single manifest validation
│   ├── validate_all()            # Batch validation
│   ├── validate_behavioral()     # Behavioral pass
│   ├── validate_implementation() # Implementation pass
│   └── run_file_tracking()       # File tracking analysis
│
├── _compare_artifacts()          # Match expected vs found artifacts
├── _compare_single()             # Compare one expected vs one found artifact
├── _find_test_files()            # Extract test files from manifest
├── _collect_test_references()    # Find artifact references in test code
└── _discover_source_files()      # Find all source files for tracking
```

### Private helpers in separate files

To keep `validate.py` focused, extract complex subroutines:

- `maid_runner/core/_type_compare.py` - Type normalization and comparison
- `maid_runner/core/_file_discovery.py` - Source file discovery for tracking

These are private modules (prefixed with `_`), imported only by `validate.py`.

## Edge Cases to Handle

### From Current Codebase (Must Preserve)

1. **`cls` and `self` parameter filtering** - When comparing method parameters, `self` and `cls` are excluded from the comparison. The manifest doesn't declare them, but they exist in the code.

2. **`@classmethod` and `@staticmethod` detection** - `cls` parameter indicates classmethod. Static methods have neither self nor cls.

3. **Generic base class support** - `class Foo(Generic[T])` should match `bases: ["Generic[T]"]` or `bases: ["Generic"]`.

4. **Module-level attributes** - Type aliases like `ManifestData = Dict[str, Any]` are detected as attributes at module scope (no `of` field).

5. **Async function detection** - `async def foo()` must match `async: true` in manifest.

6. **Private artifact exclusion** - `_helper()` functions are not flagged as unexpected in strict mode. Only public artifacts are enforced.

7. **Decorator detection** - `@property`, `@classmethod`, `@staticmethod` affect how artifacts are categorized.

8. **TypeScript special cases:**
   - Arrow functions as class properties
   - JSX/TSX component detection
   - Interface extends
   - Type union/intersection
   - Enum members
   - Namespace merging
   - Variable-to-class mapping (React.FC pattern)
   - Generator functions (function*)
   - Object property arrows excluded from module-scope functions

9. **Svelte special cases:**
   - Script tag extraction and delegation to TypeScript validator
   - Component exports

10. **Empty artifacts list** - If a FileSpec has an empty artifacts list, it's a schema error (caught in Pass 1).

11. **File path normalization** - Paths are always compared as relative to project root, with forward slashes, no leading `./`.

12. **Validation command existence check** - Before running validation commands, verify the command executable exists (e.g., `pytest` is installed). Warning if not found.
