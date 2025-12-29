# Spike: `maid manifest create` Command

**Date:** 2025-12-28
**Updated:** 2025-12-28
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
2. **Auto-supersedes** active snapshot manifests (required to "unfreeze" the file)
3. **Auto-detects** file mode (create vs edit based on file existence)
4. **Outputs JSON** for agent consumption (`--json` flag)
5. **Validates** the generated manifest before writing

## Key Concept: Snapshot Supersession

**Snapshots "freeze" code files.** Per MAID methodology:

- A **snapshot manifest** captures the complete public API of a file at a point in time
- The file is considered "frozen" until the snapshot is superseded
- To edit a snapshotted file, you **MUST** create an edit manifest that supersedes the snapshot
- This "unfreezes" the file for development

**Therefore:**
- Superseding an active snapshot is **automatic and required**, not optional
- No `--auto-supersede` flag needed for snapshots - it's the default behavior
- A `--force-supersede` flag is provided for manually superseding non-snapshot manifests

## CLI Interface

```bash
# Basic usage - creates manifest for a file with a goal
# If file has an active snapshot, it's automatically superseded
maid manifest create src/auth/service.py --goal "Add AuthService class"

# With artifacts specified (JSON format for agents)
maid manifest create src/auth/service.py \
  --goal "Add AuthService class" \
  --artifacts '[{"type": "class", "name": "AuthService"}]'

# Machine-readable output for agents
maid manifest create src/auth/service.py \
  --goal "Add login method" \
  --json \
  --quiet

# Specify task type explicitly
maid manifest create src/auth/service.py \
  --goal "Restructure auth module" \
  --task-type refactor

# Force supersede a specific non-snapshot manifest
maid manifest create src/auth/service.py \
  --goal "Complete rewrite of auth" \
  --force-supersede task-050-add-login.manifest.json

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
| `--task-type` | choice | No | auto | One of: `create`, `edit`, `refactor` |
| `--force-supersede` | string | No | - | Force supersede a specific manifest (for non-snapshots) |
| `--test-file` | string | No | auto | Path to test file for validationCommand |
| `--readonly-files` | string | No | `[]` | Comma-separated list of readonly dependencies |
| `--output-dir` | string | No | `manifests` | Directory to write manifest |
| `--task-number` | int | No | auto | Force specific task number |
| `--json` | flag | No | false | Output created manifest as JSON |
| `--quiet` | flag | No | false | Suppress informational messages |
| `--dry-run` | flag | No | false | Print manifest without writing |

## Auto-Detection Logic

### Supersede Logic (Core Behavior)

```python
def find_active_snapshot_to_supersede(file_path: str, manifests_dir: Path) -> Optional[str]:
    """Find active snapshot manifest that MUST be superseded.

    Per MAID methodology:
    - Snapshots "freeze" a file
    - To edit a snapshotted file, you MUST supersede the snapshot
    - This is automatic, not optional

    Returns:
        Path to active snapshot manifest, or None if no active snapshot exists
    """
    from maid_runner.utils import get_superseded_manifests

    superseded = get_superseded_manifests(manifests_dir)

    for manifest_path in manifests_dir.glob("task-*.manifest.json"):
        # Skip already-superseded manifests
        if manifest_path in superseded:
            continue

        manifest_data = json.load(open(manifest_path))

        # Check if this manifest references our file
        expected = manifest_data.get("expectedArtifacts", {})
        if expected.get("file") != file_path:
            continue

        # If it's an active snapshot, it MUST be superseded
        if manifest_data.get("taskType") == "snapshot":
            return str(manifest_path.name)

    return None
```

### Task Type Detection

```python
def detect_task_type(file_path: Path, will_supersede: bool) -> str:
    """Determine taskType based on context.

    Args:
        file_path: Path to the target file
        will_supersede: Whether this manifest will supersede another

    Returns:
        taskType: "create" or "edit"
    """
    if not file_path.exists():
        return "create"
    else:
        return "edit"  # Editing existing file (superseding snapshot or not)
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

### Test File Auto-Detection

```python
def detect_test_file(file_path: str, task_number: int) -> Optional[str]:
    """Generate expected test file path."""
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

## Workflow Examples

### Example 1: Creating manifest for new file (no snapshot)

```bash
$ maid manifest create src/new_module.py --goal "Add new utility module"

✓ Created manifest: manifests/task-095-add-new-utility-module.manifest.json

  Goal: Add new utility module
  File: src/new_module.py (create)

  Next steps:
  1. Write behavioral tests: tests/test_task_095_new_module.py
  2. Validate: maid validate manifests/task-095-add-new-utility-module.manifest.json --validation-mode behavioral
  3. Implement code
  4. Validate: maid validate manifests/task-095-add-new-utility-module.manifest.json
```

### Example 2: Editing file with active snapshot (auto-supersede)

```bash
$ maid manifest create src/auth/service.py --goal "Add login method"

ℹ️  Active snapshot detected: task-012-snapshot-auth-service.manifest.json
    Automatically superseding to "unfreeze" the file for editing.

✓ Created manifest: manifests/task-095-add-login-method.manifest.json

  Goal: Add login method
  File: src/auth/service.py (edit)
  Supersedes: task-012-snapshot-auth-service.manifest.json

  Next steps:
  1. Write behavioral tests: tests/test_task_095_auth_service.py
  2. Validate: maid validate manifests/task-095-add-login-method.manifest.json --validation-mode behavioral
  3. Implement code
  4. Validate: maid validate manifests/task-095-add-login-method.manifest.json
```

### Example 3: Force supersede non-snapshot manifest

```bash
$ maid manifest create src/auth/service.py \
    --goal "Complete rewrite" \
    --force-supersede task-050-add-login.manifest.json

⚠️  Force superseding non-snapshot manifest: task-050-add-login.manifest.json
    This will archive the previous manifest.

✓ Created manifest: manifests/task-095-complete-rewrite.manifest.json

  Goal: Complete rewrite
  File: src/auth/service.py (edit)
  Supersedes: task-050-add-login.manifest.json
```

### Example 4: Agent-friendly JSON output

```bash
$ maid manifest create src/auth/service.py --goal "Add login" --json --quiet
```

```json
{
  "success": true,
  "manifest_path": "manifests/task-095-add-login.manifest.json",
  "task_number": 95,
  "superseded_snapshot": "task-012-snapshot-auth-service.manifest.json",
  "manifest": {
    "goal": "Add login",
    "taskType": "edit",
    "supersedes": ["task-012-snapshot-auth-service.manifest.json"],
    "creatableFiles": [],
    "editableFiles": ["src/auth/service.py"],
    "readonlyFiles": [],
    "expectedArtifacts": {
      "file": "src/auth/service.py",
      "contains": []
    },
    "validationCommand": ["pytest", "tests/test_task_095_auth_service.py", "-v"]
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
└── test_task_097_snapshot_supersede.py      # Snapshot supersession tests
```

## Affected Components

1. **`maid_runner/cli/main.py`**
   - Add `manifest` subparser with `create` subcommand
   - Register arguments and dispatch to handler

2. **`maid_runner/cli/manifest_create.py`** (NEW)
   - `run_create_manifest()` - Main entry point
   - `_get_next_task_number()` - Find next available task number
   - `_detect_task_type()` - Auto-detect create/edit
   - `_find_active_snapshot_to_supersede()` - Find snapshot that must be superseded
   - `_generate_manifest()` - Build manifest dict
   - `_write_manifest()` - Write to file with validation

3. **`maid_runner/cli/_manifest_helpers.py`** (NEW)
   - `parse_artifacts_json()` - Parse artifacts from CLI
   - `sanitize_goal_for_filename()` - Generate safe filename
   - `generate_validation_command()` - Build validationCommand

4. **`maid_runner/utils.py`**
   - Reuse existing `get_superseded_manifests()`

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
- `_find_active_snapshot_to_supersede()` - Auto-supersede for snapshots
- `_generate_manifest()`
- `_write_manifest()`
- **File:** `maid_runner/cli/manifest_create.py` (NEW)

### Task 098: Force Supersede & Edge Cases
- `--force-supersede` for non-snapshot manifests
- Dry-run mode
- JSON output mode
- Error handling refinement
- **File:** `maid_runner/cli/manifest_create.py` (extends Task 097)

## Edge Cases to Handle

1. **No manifests directory** - Create it or error with helpful message
2. **Artifacts JSON parse error** - Clear error message with example
3. **File path doesn't exist + taskType=edit** - Warning or error
4. **Goal too long for filename** - Truncate and sanitize
5. **Manifest already exists for this goal** - Prompt or use `--force`
6. **Multiple active snapshots for same file** - Should not happen (would be a chain error), but handle gracefully
7. **Snapshot already superseded** - Skip, find next active manifest

## Success Criteria

1. `maid manifest create file.py --goal "X"` creates valid manifest
2. Active snapshot manifests are automatically superseded
3. JSON output is parseable by agents
4. Generated manifests pass `maid validate --validation-mode schema`
5. Integration with existing `maid snapshot` doesn't break

## Out of Scope (Future Work)

1. **File deletion pattern** - `status: "absent"` manifests (hold for now)
2. **File rename pattern** - Supersede + new creatableFiles (hold for now)
3. **`maid manifest list`** - List manifests for a file
4. **`maid manifest validate-chain`** - Validate chain coherence
5. **Interactive mode** - Guided manifest creation with prompts

## Design Decisions

### 1. Snapshot supersession is automatic, not optional

**Decision:** No `--auto-supersede` flag. Superseding active snapshots is mandatory per MAID methodology.

**Rationale:**
- Snapshots "freeze" code
- Editing requires "unfreezing" via supersession
- Making this optional would violate MAID principles
- The command should do the right thing by default

### 2. Force supersede for non-snapshots

**Decision:** Provide `--force-supersede <manifest>` for explicit supersession of non-snapshot manifests.

**Rationale:**
- Non-snapshot supersession is intentional, not automatic
- User must explicitly specify which manifest to supersede
- Prevents accidental supersession of active work

### 3. Test stub generation

**Decision:** Generate test stubs by default (consistent with `maid snapshot`).

**Rationale:**
- Reduces friction in the MAID workflow
- Tests are required for validation
- Add `--skip-test-stub` flag if needed

## Conclusion

The `maid manifest create` command fills a critical gap in the MAID CLI by providing programmatic manifest creation with intelligent snapshot handling. This enables AI agents to silently follow MAID methodology without human intervention in manifest authoring.

**Key insight:** Snapshot supersession is not optional - it's required to "unfreeze" a file for editing. The command handles this automatically.

**Priority: HIGH** - This is a foundational feature for the MAID Agents ecosystem.

**Next Steps:**
1. Create manifest for Task 095 (CLI registration)
2. Implement in TDD fashion following MAID workflow
3. Update documentation
