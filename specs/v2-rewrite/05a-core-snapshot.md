# MAID Runner v2 - Core Snapshot Module

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [06-validators.md](06-validators.md)

## Module Location

`maid_runner/core/snapshot.py`

## Purpose

Snapshot generation creates manifest files from existing code. This is the entry point for adopting MAID on existing projects: snapshot the current state, then use manifests for future changes.

## Public API

```python
def generate_snapshot(
    file_path: str | Path,
    *,
    project_root: str | Path = ".",
    include_private: bool = False,
) -> Manifest:
    """Generate a snapshot manifest from an existing source file.

    Analyzes the source file with the appropriate language validator
    to discover all public artifacts, then constructs a Manifest object.

    Args:
        file_path: Path to source file to snapshot.
        project_root: Project root for relative path resolution.
        include_private: If True, include private artifacts (default: only public).

    Returns:
        Manifest object representing the current state of the file.

    Raises:
        FileNotFoundError: If file_path does not exist.
        UnsupportedLanguageError: If no validator available for the file type.
    """


def generate_system_snapshot(
    manifest_dir: str | Path = "manifests/",
    *,
    project_root: str | Path = ".",
    include_private: bool = False,
) -> Manifest:
    """Generate a system-wide snapshot aggregating all tracked files.

    Discovers all source files referenced by active manifests, collects
    artifacts from each, and creates a single system-snapshot manifest.

    Args:
        manifest_dir: Directory containing existing manifests.
        project_root: Project root.
        include_private: Include private artifacts.

    Returns:
        Manifest with type=system-snapshot and all file artifacts.
    """


def save_snapshot(
    manifest: Manifest,
    *,
    output_dir: str | Path = "manifests/",
    output: str | Path | None = None,
    format: str = "yaml",
) -> Path:
    """Save a snapshot manifest to disk.

    Args:
        manifest: Manifest to save.
        output_dir: Directory for output (used if output is None).
        output: Specific output path (overrides output_dir).
        format: "yaml" (default) or "json".

    Returns:
        Path to the saved manifest file.
    """


def generate_test_stub(
    manifest: Manifest,
    *,
    output_dir: str | Path = "tests/",
) -> dict[str, str]:
    """Generate test stub files for a manifest.

    Creates one test file per source file in the manifest.

    Args:
        manifest: Manifest to generate tests for.
        output_dir: Directory for test files.

    Returns:
        Dict of file_path -> test_content for each generated stub.
    """
```

## Snapshot Flow

```
generate_snapshot("src/auth/service.py")
    │
    ├─ Resolve file path relative to project root
    │
    ├─ Read source file content
    │
    ├─ Get validator from ValidatorRegistry
    │   └─ PythonValidator for .py, TypeScriptValidator for .ts, etc.
    │
    ├─ Collect artifacts: validator.collect_implementation_artifacts(source, path)
    │
    ├─ Filter: exclude private artifacts (unless include_private=True)
    │
    ├─ Build snapshot manifest dict from artifacts
    │   └─ Use validator.generate_snapshot(source, path) for language-specific formatting
    │
    ├─ Generate slug from filename: "snapshot-auth-service"
    │
    ├─ Build Manifest dataclass:
    │   ├─ slug: "snapshot-auth-service"
    │   ├─ goal: "Snapshot of src/auth/service.py"
    │   ├─ type: "snapshot"
    │   ├─ files.snapshot: [FileSpec(path, artifacts)]
    │   ├─ validate: [("pytest", "tests/test_auth_service.py", "-v")]
    │   └─ created: current ISO timestamp
    │
    └─ Return Manifest
```

## Slug Generation for Snapshots

```python
def _snapshot_slug(file_path: str) -> str:
    """Generate slug for a snapshot manifest.

    Examples:
        "src/auth/service.py" -> "snapshot-auth-service"
        "maid_runner/validators/python.py" -> "snapshot-validators-python"
        "src/components/AuthProvider.tsx" -> "snapshot-components-auth-provider"
    """
```

## Validation Command Detection

When generating a snapshot, the validation command is inferred from the file:

```python
def _infer_validation_command(file_path: str) -> tuple[str, ...]:
    """Infer the test command for a snapshot.

    Heuristics:
    1. Look for matching test file:
       - src/auth/service.py -> tests/test_auth_service.py (Python)
       - src/auth/service.ts -> tests/auth/service.test.ts (TypeScript)
    2. If test file found, use appropriate runner:
       - .py -> ("pytest", test_path, "-v")
       - .ts/.tsx -> ("vitest", "run", test_path)
    3. If no test file found:
       - Python: ("pytest", "tests/", "-v") (run all tests)
       - TypeScript: ("vitest", "run")
    """
```

## System Snapshot

System snapshot aggregates artifacts from ALL tracked source files:

```
generate_system_snapshot("manifests/")
    │
    ├─ Build ManifestChain from manifest_dir
    │
    ├─ Get all tracked file paths from chain
    │
    ├─ For each tracked file:
    │   ├─ Read source
    │   ├─ Get validator
    │   ├─ Collect artifacts
    │   └─ Build FileSpec
    │
    ├─ Build Manifest:
    │   ├─ slug: "system-snapshot"
    │   ├─ goal: "System-wide snapshot of all tracked files"
    │   ├─ type: "system-snapshot"
    │   ├─ files.snapshot: [FileSpec for each file]
    │   └─ validate: [("pytest", "tests/", "-v")]
    │
    └─ Return Manifest
```

## Supersession Handling

When snapshotting a file that already has a snapshot manifest:

```python
def _find_existing_snapshot(file_path: str, manifest_dir: Path) -> str | None:
    """Find existing snapshot manifest for a file.

    Scans manifest_dir for snapshot manifests that target this file.
    Returns the slug of the existing snapshot, or None.
    """
```

If an existing snapshot is found, the new snapshot includes it in `supersedes`:

```yaml
schema: "2"
goal: "Snapshot of src/auth/service.py"
type: snapshot
supersedes: [snapshot-auth-service]  # supersedes the old snapshot
# ...
```

## Test Stub Generation

Test stubs are generated per-file using the language validator's `generate_test_stub()` method:

```python
def generate_test_stub(manifest: Manifest, *, output_dir: str | Path = "tests/") -> dict[str, str]:
    """Generate test stubs for all files in a manifest.

    Returns dict mapping test file path -> content.
    Does NOT write files to disk (caller decides).
    """
    stubs = {}
    for file_spec in manifest.all_file_specs:
        validator = ValidatorRegistry.get(file_spec.path)
        # Convert ArtifactSpec -> FoundArtifact for the validator
        found_artifacts = [_spec_to_found(a) for a in file_spec.artifacts]
        content = validator.generate_test_stub(found_artifacts, file_spec.path)
        if content:
            test_path = _infer_test_path(file_spec.path, output_dir)
            stubs[test_path] = content
    return stubs
```

### Test Path Inference

```python
def _infer_test_path(source_path: str, test_dir: str) -> str:
    """Infer test file path from source path.

    Examples:
        "src/auth/service.py" -> "tests/test_auth_service.py"
        "src/components/Auth.tsx" -> "tests/components/Auth.test.tsx"
        "src/utils.py" -> "tests/test_utils.py"
    """
```
