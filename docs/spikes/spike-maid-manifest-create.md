# Spike: `maid manifest create` Command

**Date:** 2025-12-28
**Status:** Spike Complete - Ready for Implementation
**Goal:** Enable programmatic manifest creation to support silent MAID automation in agents

## Problem Statement

Currently, creating manifests requires:
1. Manually authoring JSON files
2. Determining the next task number by scanning existing manifests
3. Figuring out which existing manifests to supersede
4. Understanding whether to use `creatableFiles` vs `editableFiles`

This friction makes MAID methodology cumbersome for both humans and AI agents. We need CLI primitives that handle this automatically.

## Proposed Solution

Add a `maid manifest create` command that:
1. **Auto-numbers** manifests (finds next task number)
2. **Auto-supersedes** relevant snapshot manifests
3. **Auto-detects** file mode (create vs edit based on file existence)
4. **Outputs JSON** for agent consumption (`--json` flag)
5. **Validates** the generated manifest before writing

## CLI Interface

```bash
# Basic usage - creates manifest for a file with a goal
maid manifest create src/auth/service.py --goal "Add AuthService class"

# With artifacts specified (JSON format for agents)
maid manifest create src/auth/service.py \
  --goal "Add AuthService class" \
  --artifacts '[{"type": "class", "name": "AuthService"}]'

# Auto-detect and supersede existing manifests for this file
maid manifest create src/auth/service.py \
  --goal "Refactor authentication" \
  --auto-supersede

# Machine-readable output for agents
maid manifest create src/auth/service.py \
  --goal "Add login method" \
  --json \
  --quiet

# Specify task type explicitly
maid manifest create src/auth/service.py \
  --goal "Restructure auth module" \
  --task-type refactor

# Specify test file for validationCommand
maid manifest create src/auth/service.py \
  --goal "Add AuthService" \
  --test-file tests/test_auth_service.py

# Skip writing - just print what would be created (dry-run)
maid manifest create src/auth/service.py \
  --goal "Add feature" \
  --dry-run

# Force specific task number (for rare cases)
maid manifest create src/auth/service.py \
  --goal "Add feature" \
  --task-number 100
```

## Arguments & Flags

| Argument/Flag | Type | Required | Default | Description |
|---------------|------|----------|---------|-------------|
| `file_path` | positional | Yes | - | Path to the file this manifest describes |
| `--goal` | string | Yes | - | Concise goal description for the manifest |
| `--artifacts` | JSON string | No | `[]` | JSON array of artifact definitions |
| `--task-type` | choice | No | auto | One of: `create`, `edit`, `refactor`, `snapshot` |
| `--auto-supersede` | flag | No | false | Automatically supersede existing manifests for this file |
| `--test-file` | string | No | auto | Path to test file for validationCommand |
| `--readonly-files` | string | No | `[]` | Comma-separated list of readonly dependencies |
| `--output-dir` | string | No | `manifests` | Directory to write manifest |
| `--task-number` | int | No | auto | Force specific task number |
| `--json` | flag | No | false | Output created manifest as JSON |
| `--quiet` | flag | No | false | Suppress informational messages |
| `--dry-run` | flag | No | false | Print manifest without writing |

## Auto-Detection Logic

### Task Type Detection

```python
def detect_task_type(file_path: Path, has_supersedes: bool) -> str:
    """Determine taskType based on context."""
    if not file_path.exists():
        return "create"
    elif has_supersedes:
        return "edit"  # Superseding implies editing existing code
    else:
        return "edit"  # File exists, we're editing it
```

### File Mode Detection

```python
def detect_file_mode(file_path: Path) -> str:
    """Determine if file should be in creatableFiles or editableFiles."""
    if file_path.exists():
        return "editableFiles"
    else:
        return "creatableFiles"
```

### Auto-Supersede Logic

```python
def find_manifests_to_supersede(file_path: str, manifests_dir: Path) -> List[str]:
    """Find existing manifests that should be superseded."""
    to_supersede = []

    for manifest_path in manifests_dir.glob("task-*.manifest.json"):
        manifest_data = json.load(open(manifest_path))

        # Check if this manifest references our file
        expected = manifest_data.get("expectedArtifacts", {})
        if expected.get("file") == file_path:
            # Only supersede snapshots by default
            if manifest_data.get("taskType") == "snapshot":
                to_supersede.append(str(manifest_path.name))

    return to_supersede
```

### Test File Auto-Detection

```python
def detect_test_file(file_path: str, task_number: int) -> Optional[str]:
    """Generate expected test file path."""
    # Extract base name
    path = Path(file_path)
    base_name = path.stem.replace("_", "-")

    # Python: tests/test_task_XXX_name.py
    if file_path.endswith(".py"):
        return f"tests/test_task_{task_number:03d}_{base_name}.py"

    # TypeScript: tests/task-XXX-name.spec.ts
    elif file_path.endswith((".ts", ".tsx")):
        return f"tests/task-{task_number:03d}-{base_name}.spec.ts"

    return None
```

## Output Format

### Standard Output (human-readable)

```
✓ Created manifest: manifests/task-095-add-authservice.manifest.json

  Goal: Add AuthService class
  File: src/auth/service.py (create)
  Supersedes: task-012-snapshot-auth-service.manifest.json

  Next steps:
  1. Write behavioral tests: tests/test_task_095_add_authservice.py
  2. Validate: maid validate manifests/task-095-add-authservice.manifest.json --validation-mode behavioral
  3. Implement code
  4. Validate: maid validate manifests/task-095-add-authservice.manifest.json
```

### JSON Output (`--json` flag)

```json
{
  "success": true,
  "manifest_path": "manifests/task-095-add-authservice.manifest.json",
  "task_number": 95,
  "manifest": {
    "goal": "Add AuthService class",
    "taskType": "create",
    "supersedes": ["task-012-snapshot-auth-service.manifest.json"],
    "creatableFiles": ["src/auth/service.py"],
    "editableFiles": [],
    "readonlyFiles": [],
    "expectedArtifacts": {
      "file": "src/auth/service.py",
      "contains": [
        {"type": "class", "name": "AuthService"}
      ]
    },
    "validationCommand": ["pytest", "tests/test_task_095_add_authservice.py", "-v"]
  }
}
```

## Implementation Structure

### New Files

```
maid_runner/cli/
├── manifest_create.py      # Main command implementation (~300 lines)
└── _manifest_helpers.py    # Private helpers for manifest operations (~150 lines)
```

### Modified Files

```
maid_runner/cli/main.py     # Add subcommand registration (~30 lines added)
```

### Test Files

```
tests/
├── test_task_095_manifest_create_cli.py     # CLI integration tests
├── test_task_096_manifest_create_logic.py   # Unit tests for logic
└── test_task_097_auto_supersede.py          # Auto-supersede tests
```

## Affected Components

1. **`maid_runner/cli/main.py`**
   - Add `manifest` subparser with `create` subcommand
   - Register arguments and dispatch to handler

2. **`maid_runner/cli/manifest_create.py`** (NEW)
   - `run_create_manifest()` - Main entry point
   - `_get_next_task_number()` - Find next available task number
   - `_detect_task_type()` - Auto-detect create/edit/refactor
   - `_find_manifests_to_supersede()` - Auto-supersede logic
   - `_generate_manifest()` - Build manifest dict
   - `_write_manifest()` - Write to file with validation

3. **`maid_runner/cli/_manifest_helpers.py`** (NEW)
   - `parse_artifacts_json()` - Parse artifacts from CLI
   - `sanitize_goal_for_filename()` - Generate safe filename
   - `generate_validation_command()` - Build validationCommand

4. **`maid_runner/utils.py`**
   - Potentially add shared helpers (or use existing ones)

## Complexity Estimate

| Component | Effort | Notes |
|-----------|--------|-------|
| CLI registration in main.py | 0.5 days | Straightforward following existing patterns |
| Core manifest_create.py | 2 days | Main logic, auto-detection, validation |
| _manifest_helpers.py | 1 day | Parsing, filename generation, etc. |
| Tests | 2 days | Comprehensive coverage needed |
| Documentation | 0.5 days | Update CLAUDE.md, README |
| **Total** | **~6 days** | ~1 week of work |

## Task Breakdown (MAID Manifests)

This feature requires **4-5 separate manifests** (one per file):

### Task 095: CLI Registration (`main.py`)
- Add `manifest create` subparser
- Register all arguments
- Dispatch to handler
- **File:** `maid_runner/cli/main.py`

### Task 096: Manifest Helpers (`_manifest_helpers.py`)
- `parse_artifacts_json()`
- `sanitize_goal_for_filename()`
- `generate_validation_command()`
- **File:** `maid_runner/cli/_manifest_helpers.py` (NEW)

### Task 097: Core Create Logic (`manifest_create.py`)
- `run_create_manifest()` main function
- `_get_next_task_number()`
- `_detect_task_type()`
- `_generate_manifest()`
- `_write_manifest()`
- **File:** `maid_runner/cli/manifest_create.py` (NEW)

### Task 098: Auto-Supersede Logic
- `_find_manifests_to_supersede()`
- Integration with create flow
- **File:** `maid_runner/cli/manifest_create.py` (extends Task 097)

### Task 099: Integration & Edge Cases
- Dry-run mode
- JSON output mode
- Error handling refinement
- **File:** `maid_runner/cli/manifest_create.py` (extends Task 097)

## Edge Cases to Handle

1. **No manifests directory** - Create it or error with helpful message
2. **Artifacts JSON parse error** - Clear error message with example
3. **File path doesn't exist + taskType=edit** - Warning or error
4. **Circular supersedes** - Validate before writing
5. **Goal too long for filename** - Truncate and sanitize
6. **Manifest already exists for this goal** - Prompt or use `--force`
7. **Multiple snapshots for same file** - Supersede all of them

## Success Criteria

1. `maid manifest create file.py --goal "X"` creates valid manifest
2. Auto-supersede correctly identifies snapshot manifests
3. JSON output is parseable by agents
4. Generated manifests pass `maid validate --validation-mode schema`
5. Integration with existing `maid snapshot` doesn't break

## Future Enhancements (Not in Scope)

1. **`maid manifest list`** - List manifests for a file
2. **`maid manifest suggest-supersedes`** - Just show what would be superseded
3. **`maid manifest validate-chain`** - Validate chain coherence
4. **Interactive mode** - Guided manifest creation with prompts

## Open Questions

1. **Should `--auto-supersede` be the default?**
   - Pro: Less manual work
   - Con: Could accidentally supersede something unexpected
   - **Recommendation:** Default OFF, but print suggestions when not used

2. **Should we generate test stubs automatically?**
   - `maid snapshot` does this
   - Could add `--skip-test-stub` flag (default: generate stubs)
   - **Recommendation:** Yes, consistent with `maid snapshot`

3. **How to handle multiple files?**
   - MAID principle: one file per manifest
   - Could support `maid manifest create file1.py file2.py` as multiple manifests
   - **Recommendation:** Single file only, error if multiple given

## Conclusion

The `maid manifest create` command fills a critical gap in the MAID CLI by providing programmatic manifest creation. This enables AI agents to silently follow MAID methodology without human intervention in manifest authoring.

**Priority: HIGH** - This is a foundational feature for the MAID Agents ecosystem.

**Next Steps:**
1. Create manifest for Task 095 (CLI registration)
2. Implement in TDD fashion following MAID workflow
3. Update documentation
