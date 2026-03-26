# MAID Runner v2 - Core Manifest Module

**References:** [01-architecture.md](01-architecture.md), [02-manifest-schema-v2.md](02-manifest-schema-v2.md), [03-data-types.md](03-data-types.md), [13-backward-compatibility.md](13-backward-compatibility.md)

## Module Location

- `maid_runner/core/manifest.py` - Loading and schema validation
- `maid_runner/core/chain.py` - Chain resolution and merge

## manifest.py - Manifest Loading

### Responsibilities

1. Load manifest files from disk (YAML v2 or JSON v1)
2. Detect format version and dispatch to appropriate parser
3. Schema-validate against JSON Schema
4. Parse into `Manifest` dataclass
5. Normalize all representations to canonical form

### Public API

```python
def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a manifest file.

    Supports:
    - .manifest.yaml (v2 format)
    - .manifest.json (v1 format, auto-converted via compat layer)

    Args:
        path: Absolute or relative path to manifest file.

    Returns:
        Manifest dataclass.

    Raises:
        ManifestLoadError: If file cannot be read or parsed.
        ManifestSchemaError: If manifest fails schema validation.
    """


def load_manifest_raw(path: str | Path) -> dict:
    """Load manifest as raw dict without parsing into dataclass.

    Useful for schema inspection and tooling.
    """


def save_manifest(manifest: Manifest, path: str | Path) -> None:
    """Save a Manifest to disk in YAML v2 format.

    Args:
        manifest: The manifest to save.
        path: Destination path (should end in .manifest.yaml).
    """


def validate_manifest_schema(data: dict, schema_version: str = "2") -> list[str]:
    """Validate raw manifest dict against JSON Schema.

    Returns:
        List of validation error messages (empty if valid).
    """


def slug_from_path(path: str | Path) -> str:
    """Extract manifest slug from file path.

    Examples:
        "manifests/add-jwt-auth.manifest.yaml" -> "add-jwt-auth"
        "manifests/task-001-add-schema.manifest.json" -> "task-001-add-schema"
    """
```

### Loading Flow

```
load_manifest(path)
    │
    ├─ Read file contents
    │
    ├─ Detect format:
    │   ├─ .yaml/.yml -> parse YAML
    │   └─ .json -> parse JSON
    │
    ├─ Detect version:
    │   ├─ Has "schema: '2'" -> v2 format
    │   └─ No schema field or "version: '1'" -> v1 format
    │       └─ Convert via compat/v1_loader.convert_v1_to_v2(data)
    │
    ├─ Schema validate against manifest.v2.schema.json
    │
    ├─ Parse into Manifest dataclass:
    │   ├─ Extract slug from filename
    │   ├─ Parse files.create -> list[FileSpec] with mode=CREATE
    │   ├─ Parse files.edit -> list[FileSpec] with mode=EDIT
    │   ├─ Parse files.read -> list[str]
    │   ├─ Parse files.delete -> list[DeleteSpec]
    │   ├─ Parse files.snapshot -> list[FileSpec] with mode=SNAPSHOT
    │   ├─ Parse validate -> normalize to tuple[tuple[str, ...], ...]
    │   └─ Parse artifacts within each FileSpec
    │
    └─ Return Manifest
```

### Artifact Parsing

Each artifact in a FileSpec's `artifacts` list is parsed into an `ArtifactSpec`:

```python
def _parse_artifact(data: dict) -> ArtifactSpec:
    """Parse a raw artifact dict into ArtifactSpec.

    Handles:
    - kind mapping to ArtifactKind enum
    - args list to tuple of ArgSpec
    - returns normalization (always string or None)
    - of field for methods and class attributes
    """
```

### Validation Command Normalization

The `validate` field accepts two forms and normalizes to a consistent internal format:

```yaml
# Form 1: Single command (list of strings)
validate:
  - pytest tests/test_auth.py -v

# Form 2: Multiple commands (list of list of strings)
validate:
  - [pytest, tests/test_auth.py, -v]
  - [vitest, run, tests/auth.test.ts]
```

Internally, commands are stored as `tuple[tuple[str, ...], ...]`:
- Form 1: `(("pytest", "tests/test_auth.py", "-v"),)`
- Form 2: `(("pytest", "tests/test_auth.py", "-v"), ("vitest", "run", "tests/auth.test.ts"))`

**Detection logic:**
- If `validate` is a list of strings -> single command -> wrap in outer tuple
- If `validate` is a list of lists -> multiple commands -> convert each to tuple

### Error Types

```python
class ManifestLoadError(Exception):
    """Raised when a manifest file cannot be loaded."""
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load manifest {path}: {reason}")


class ManifestSchemaError(Exception):
    """Raised when a manifest fails schema validation."""
    def __init__(self, path: str, errors: list[str]):
        self.path = path
        self.errors = errors
        super().__init__(f"Schema validation failed for {path}: {'; '.join(errors)}")
```

---

## chain.py - Manifest Chain Resolution

### Responsibilities

1. Discover all manifests in a directory
2. Resolve supersession relationships (which manifests replace which)
3. Determine the set of active (non-superseded) manifests
4. Merge artifact declarations across active manifests for each file
5. Provide efficient lookup: file -> merged artifacts

### Public API

```python
class ManifestChain:
    """Resolves and manages the chain of active manifests.

    The chain represents the accumulated state of all manifest declarations,
    with superseded manifests excluded. It provides merged artifact views
    per file, combining declarations from all active manifests that
    reference each file.

    Usage:
        chain = ManifestChain("manifests/")
        active = chain.active_manifests()
        artifacts = chain.merged_artifacts_for("src/auth/service.py")
    """

    def __init__(self, manifest_dir: str | Path, project_root: str | Path = "."):
        """Initialize chain from a manifest directory.

        Args:
            manifest_dir: Directory containing manifest files.
            project_root: Project root for resolving relative paths.

        Raises:
            FileNotFoundError: If manifest_dir does not exist.
        """

    @property
    def all_manifests(self) -> list[Manifest]:
        """All loaded manifests (including superseded ones)."""

    def active_manifests(self) -> list[Manifest]:
        """Manifests that are NOT superseded by any other manifest.

        Returns manifests sorted by created timestamp (oldest first).
        Manifests without timestamps sort after those with timestamps.
        """

    def superseded_manifests(self) -> list[Manifest]:
        """Manifests that have been superseded by another manifest."""

    def is_superseded(self, slug: str) -> bool:
        """Check if a manifest has been superseded."""

    def superseded_by(self, slug: str) -> Optional[str]:
        """Return the slug of the manifest that supersedes this one, or None."""

    def manifests_for_file(self, path: str) -> list[Manifest]:
        """All active manifests that reference a given file path.

        Includes manifests where the file appears in create, edit,
        snapshot, or delete sections (not read-only).
        """

    def merged_artifacts_for(self, path: str) -> list[ArtifactSpec]:
        """Merge artifact declarations from all active manifests for a file.

        When multiple manifests declare artifacts for the same file,
        they are merged using merge_key() for deduplication. Later
        manifests (by created timestamp) take precedence over earlier ones.

        Returns:
            Combined list of unique ArtifactSpec objects for the file.
        """

    def file_mode_for(self, path: str) -> Optional[FileMode]:
        """Determine the effective file mode across the chain.

        If any manifest declares the file in 'create', the mode is CREATE.
        If all references are 'edit', the mode is EDIT.
        If only 'read', returns READ.
        If latest declares 'delete', returns DELETE.

        Returns None if file is not referenced in any manifest.
        """

    def all_tracked_paths(self) -> set[str]:
        """All file paths referenced (writable) in any active manifest."""

    def validate_supersession_integrity(self) -> list[str]:
        """Check for supersession problems.

        Checks:
        - Superseded manifests exist
        - No circular supersession
        - No manifest supersedes itself

        Returns:
            List of error messages (empty if clean).
        """

    def reload(self) -> None:
        """Reload all manifests from disk. Useful after file changes."""
```

### Chain Resolution Algorithm

```
1. Load all .manifest.yaml and .manifest.json files from manifest_dir
2. For each manifest, record its supersedes list
3. Build supersession graph: slug -> set of superseded slugs
4. Detect and report circular supersession
5. Compute active set: all manifests NOT in any supersedes list
6. Sort active manifests by created timestamp
7. Build file index: path -> list of active manifests referencing it
8. Cache results for repeated lookups
```

### Artifact Merge Strategy

When multiple active manifests declare artifacts for the same file:

```
File: src/auth/service.py

Manifest A (created: 2025-06-01):
  - class AuthService
  - method AuthService.login

Manifest B (created: 2025-06-15):
  - method AuthService.verify
  - method AuthService.login (updated signature)

Merged result:
  - class AuthService            (from A, not overridden)
  - method AuthService.login     (from B, later manifest wins)
  - method AuthService.verify    (from B, new addition)
```

**Merge algorithm:**
1. Collect artifacts from all active manifests for the file, ordered by `created` timestamp
2. Build a dict keyed by `artifact.merge_key()`
3. Later artifacts overwrite earlier ones with the same key
4. Return the values as a list

### Caching

The chain caches:
- Loaded manifests (invalidated by `reload()`)
- Active/superseded sets
- Per-file manifest index
- Per-file merged artifacts

Cache is populated lazily on first access. Calling `reload()` clears all caches.

### Manifest Discovery

```python
def _discover_manifest_files(manifest_dir: Path) -> list[Path]:
    """Find all manifest files in a directory.

    Matches:
    - *.manifest.yaml
    - *.manifest.yml
    - *.manifest.json

    Returns paths sorted alphabetically.
    """
```

### Edge Cases

1. **Empty manifest directory** - Returns empty chain, no errors
2. **Superseded manifest references non-existent slug** - Warning (not error), supersession is ignored
3. **Circular supersession** - Error reported via `validate_supersession_integrity()`
4. **Same file in create and edit across manifests** - CREATE takes precedence (strictest mode)
5. **Manifest with no created timestamp** - Sorts after timestamped manifests; within untimed group, sorted alphabetically by slug
6. **V1 and V2 manifests mixed** - Both are loaded and converted to Manifest dataclass; chain treats them identically
