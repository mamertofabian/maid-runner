# MAID Runner v2 - Backward Compatibility

**References:** [00-overview.md](00-overview.md), [02-manifest-schema-v2.md](02-manifest-schema-v2.md), [04-core-manifest.md](04-core-manifest.md)

## Purpose

Existing MAID Runner users have v1 JSON manifests in their projects. The v2 rewrite MUST load and validate these manifests without requiring users to manually convert them.

## Module Location

`maid_runner/compat/v1_loader.py`

## V1 Format Reference

V1 manifests are JSON files with this structure:

```json
{
  "goal": "Description",
  "taskType": "create|edit|refactor|snapshot|system-snapshot",
  "supersedes": [],
  "creatableFiles": ["path/to/new.py"],
  "editableFiles": ["path/to/existing.py"],
  "readonlyFiles": ["path/to/dep.py", "tests/test_file.py"],
  "expectedArtifacts": {
    "file": "path/to/file.py",
    "status": "present|absent",
    "contains": [
      {
        "type": "class|function|attribute|parameter|interface|type|enum|namespace",
        "name": "artifact_name",
        "class": "ParentClass",
        "description": "...",
        "artifactKind": "...",
        "bases": ["Base1"],
        "function": "parent_func",
        "parameters": [{"name": "x", "type": "str"}],
        "args": [{"name": "x", "type": "str", "default": "None"}],
        "returns": "ReturnType" | {"type": "ReturnType"},
        "raises": ["ValueError"]
      }
    ]
  },
  "systemArtifacts": [...],
  "validationCommand": ["pytest", "tests/test.py", "-v"],
  "validationCommands": [["pytest", "..."], ["vitest", "..."]],
  "metadata": { "author": "...", "created": "...", "tags": [...], "priority": "..." },
  "version": "1",
  "description": "..."
}
```

### V1 Constraints
- `expectedArtifacts` is a single object (one file per manifest)
- `systemArtifacts` is an array of file objects (only for system-snapshot)
- `validationCommand` (singular) is legacy; `validationCommands` (plural) is enhanced
- `parameters` is legacy; `args` is enhanced
- `returns` can be string or `{"type": "string"}`
- `type: "function"` + `class: "X"` = method of class X
- No `schema` field (or `version: "1"`)

## Conversion API

```python
# maid_runner/compat/v1_loader.py

def is_v1_manifest(data: dict) -> bool:
    """Detect if a manifest dict is v1 format.

    V1 indicators:
    - No "schema" field
    - Has "version": "1" (optional in v1)
    - Has "expectedArtifacts" as object with "file" and "contains"
    - Has "creatableFiles" or "editableFiles" (v1 field names)
    - Has "validationCommand" (singular, v1 field name)
    """


def convert_v1_to_v2(data: dict) -> dict:
    """Convert a v1 manifest dict to v2 format.

    This produces a dict that conforms to the v2 schema and can be
    parsed into a Manifest dataclass by the standard loader.

    Returns:
        Dict in v2 format.
    """


def convert_v1_file(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    """Convert a v1 JSON manifest file to v2 YAML format.

    If output_path is None, writes to same directory with .manifest.yaml extension.

    Returns:
        Path to the output file.
    """
```

## Conversion Rules

### Field Mapping

| V1 Field | V2 Field | Conversion |
|----------|----------|-----------|
| `goal` | `goal` | Direct copy |
| `description` | `description` | Direct copy |
| `taskType` | `type` | Direct rename: "create"->"feature" for new files, else same |
| `supersedes` | `supersedes` | Convert full paths to slugs |
| `creatableFiles` | `files.create` | Each path becomes a FileSpec |
| `editableFiles` | `files.edit` | Each path becomes a FileSpec |
| `readonlyFiles` | `files.read` | Direct copy as string list |
| `expectedArtifacts` | Merged into `files.create` or `files.edit` | See below |
| `systemArtifacts` | `files.snapshot` (multiple entries) | Each item becomes a FileSpec |
| `validationCommand` | `validate` | Wrap as single command |
| `validationCommands` | `validate` | Direct copy as list of commands |
| `metadata` | `metadata` | Direct copy |
| `version` | `schema` | Set to "2" |

### Artifact Conversion

```python
def _convert_artifact(v1_artifact: dict) -> dict:
    """Convert a v1 artifact to v2 format.

    Key transformations:
    - type: "function" + class: "X" -> kind: "method", of: "X"
    - type: "function" (no class) -> kind: "function"
    - type: "attribute" + class: "X" -> kind: "attribute", of: "X"
    - type: "attribute" (no class) -> kind: "attribute"
    - type: "class" -> kind: "class"
    - type: "interface" -> kind: "interface"
    - type: "type" -> kind: "type"
    - type: "enum" -> kind: "enum"
    - type: "namespace" -> kind: "namespace"
    - parameters -> args (if args not present)
    - returns: {"type": "X"} -> returns: "X"
    - function: "X" -> (parameter of function, not supported in v2 directly)
    """
```

### Expected Artifacts -> FileSpec Conversion

V1 `expectedArtifacts` is a single object targeting one file. In v2, artifacts are nested inside `files.create` or `files.edit`:

```python
def _convert_expected_artifacts(v1_data: dict) -> None:
    """Move expectedArtifacts into the appropriate files section.

    Algorithm:
    1. Get the file path from expectedArtifacts.file
    2. Convert each artifact in expectedArtifacts.contains
    3. Determine if file is in creatableFiles or editableFiles
    4. Create a FileSpec entry in the appropriate section
    5. Remove expectedArtifacts from top level

    If the file is in creatableFiles:
        files.create entry with artifacts
    If the file is in editableFiles:
        files.edit entry with artifacts
    If neither (edge case):
        files.edit entry with artifacts (permissive default)
    """
```

### Supersedes Path -> Slug Conversion

V1 uses full paths: `"supersedes": ["manifests/task-001-add-schema.manifest.json"]`
V2 uses slugs: `"supersedes": ["task-001-add-schema"]`

```python
def _path_to_slug(path: str) -> str:
    """Convert manifest path to slug.

    "manifests/task-001-add-schema.manifest.json" -> "task-001-add-schema"
    "task-001-add-schema.manifest.json" -> "task-001-add-schema"
    """
    name = Path(path).name
    # Remove .manifest.json or .manifest.yaml
    for suffix in [".manifest.json", ".manifest.yaml", ".manifest.yml"]:
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name
```

### TaskType Conversion

V1 uses `taskType` with values that map directly:

| V1 taskType | V2 type |
|-------------|---------|
| `"create"` | `"feature"` (if has creatableFiles) or `"feature"` |
| `"edit"` | `"fix"` or `"feature"` (context-dependent; default to `"feature"`) |
| `"refactor"` | `"refactor"` |
| `"snapshot"` | `"snapshot"` |
| `"system-snapshot"` | `"system-snapshot"` |

Note: V1 "create" and "edit" don't map perfectly to v2 feature/fix. We default to "feature" for both, since the task type is informational, not behavioral.

### System Artifacts Conversion

V1 `systemArtifacts` is an array of `{file, contains}` objects for system snapshots:

```json
{
  "taskType": "system-snapshot",
  "systemArtifacts": [
    {"file": "src/a.py", "contains": [...]},
    {"file": "src/b.py", "contains": [...]}
  ]
}
```

V2 equivalent:

```yaml
type: system-snapshot
files:
  snapshot:
    - path: src/a.py
      artifacts: [...]
    - path: src/b.py
      artifacts: [...]
```

### Parameter Type ("parameter" artifact type)

V1 has `type: "parameter"` with `function: "parent"` for tracking function parameters as separate artifacts. V2 does NOT have a separate `kind: "parameter"`. Parameters are tracked as part of the function's `args` list.

Conversion: Skip `type: "parameter"` artifacts. They are redundant with the function's `args` declaration.

## Auto-Detection in `load_manifest()`

```python
# In core/manifest.py

def load_manifest(path: str | Path) -> Manifest:
    path = Path(path)

    # Read raw content
    if path.suffix == ".json":
        data = json.loads(path.read_text())
    elif path.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(path.read_text())
    else:
        raise ManifestLoadError(path, f"Unknown extension: {path.suffix}")

    # Detect version
    if is_v1_manifest(data):
        data = convert_v1_to_v2(data)

    # Now data is in v2 format - validate and parse
    errors = validate_manifest_schema(data, schema_version="2")
    if errors:
        raise ManifestSchemaError(str(path), errors)

    return _parse_manifest(data, path)
```

## Batch Conversion Tool

For users who want to convert their entire manifest directory:

```bash
# Convert all v1 manifests to v2 YAML
maid manifest convert manifests/ --output-dir manifests-v2/

# Convert a single manifest
maid manifest convert manifests/task-001.manifest.json

# Dry-run (show what would be generated)
maid manifest convert manifests/ --dry-run
```

This is a CLI convenience command, not required for operation (v1 manifests work without conversion).

## Edge Cases

1. **Mixed v1 and v2 in same directory** - Both load fine. Chain resolution treats them identically after conversion.

2. **V1 manifest with empty supersedes array** - Common pattern (`"supersedes": []`). Converted to empty tuple.

3. **V1 manifest without taskType** - Defaults to `type: "feature"` in v2.

4. **V1 manifest with both parameters and args** - `args` takes precedence (enhanced format).

5. **V1 manifest with returns as object** - `{"type": "bool"}` -> `"bool"` (string).

6. **V1 manifest referencing non-existent superseded manifest** - Warning, not error (same behavior as current v1).

7. **V1 manifest with metadata.created** - Mapped to v2 `created` field.

8. **V1 snapshot manifests** - `taskType: "snapshot"` with expectedArtifacts becomes `type: snapshot` with `files.snapshot`.

## Testing

### Test Coverage for Compat Layer

```python
# tests/compat/test_v1_loader.py

class TestV1Detection:
    def test_v1_with_expected_artifacts(self):
        """Detect v1 by presence of expectedArtifacts object."""

    def test_v2_not_detected_as_v1(self):
        """V2 manifest with schema field not detected as v1."""

    def test_v1_with_version_field(self):
        """V1 with explicit version: "1" detected correctly."""


class TestV1Conversion:
    def test_simple_create(self):
        """Convert simple v1 create manifest."""

    def test_edit_with_artifacts(self):
        """Convert v1 edit manifest with expectedArtifacts."""

    def test_method_conversion(self):
        """V1 type:function + class:X -> v2 kind:method + of:X."""

    def test_returns_object_to_string(self):
        """V1 returns: {type: "bool"} -> v2 returns: "bool"."""

    def test_supersedes_path_to_slug(self):
        """Full paths converted to slugs."""

    def test_system_artifacts(self):
        """V1 systemArtifacts converted to files.snapshot."""

    def test_validation_command_singular(self):
        """V1 validationCommand -> v2 validate (wrapped)."""

    def test_validation_commands_plural(self):
        """V1 validationCommands -> v2 validate (direct)."""

    def test_parameter_artifacts_skipped(self):
        """V1 type:parameter artifacts are omitted (redundant)."""

    def test_real_project_manifests(self, fixtures_dir):
        """Convert actual v1 manifests from this project's history."""
        # Load a few representative v1 manifests and verify conversion
```

### Integration Test

```python
class TestV1ManifestValidation:
    def test_validate_v1_manifest(self, tmp_project):
        """V1 JSON manifest validates successfully through full pipeline."""
        # Write a v1 manifest + corresponding source code
        # Call validate() and verify it passes
```
