"""Initialize MAID methodology in an existing repository.

This module provides the 'maid init' command to set up the necessary
directory structure and documentation for using MAID in a project.
"""

import json
import shutil
from pathlib import Path


def load_claude_manifest() -> dict:
    """Load and parse the Claude files manifest.json.

    Returns:
        Dictionary containing agents and commands configuration
    """
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent
    manifest_path = maid_runner_package / "claude" / "manifest.json"

    with open(manifest_path) as f:
        return json.load(f)


def get_distributable_files(manifest: dict, file_type: str) -> list:
    """Get list of distributable files from manifest for a given file type.

    Args:
        manifest: The loaded manifest dictionary
        file_type: Either "agents" or "commands"

    Returns:
        List of filenames that should be distributed
    """
    if file_type not in manifest:
        return []
    return manifest[file_type].get("distributable", [])


# MAID section markers for idempotent CLAUDE.md handling
MAID_SECTION_START = "<!-- MAID-SECTION-START -->"
MAID_SECTION_END = "<!-- MAID-SECTION-END -->"


def has_maid_markers(content: str) -> bool:
    """Check if content contains MAID section markers.

    Args:
        content: The text content to check

    Returns:
        True if both start and end markers are present, False otherwise
    """
    return MAID_SECTION_START in content and MAID_SECTION_END in content


def replace_maid_section(existing_content: str, new_maid_content: str) -> str:
    """Replace content between MAID markers with new content.

    Args:
        existing_content: The existing file content with MAID markers
        new_maid_content: The new MAID documentation to insert

    Returns:
        Updated content with MAID section replaced, or original if markers
        are missing or malformed (e.g., reversed order)
    """
    if not has_maid_markers(existing_content):
        return existing_content

    start_idx = existing_content.index(MAID_SECTION_START)
    end_idx = existing_content.index(MAID_SECTION_END) + len(MAID_SECTION_END)

    # Check for malformed markers (END before START)
    if start_idx >= existing_content.index(MAID_SECTION_END):
        return existing_content

    before = existing_content[:start_idx]
    after = existing_content[end_idx:]

    wrapped_new = wrap_with_markers(new_maid_content)

    return before + wrapped_new + after


def wrap_with_markers(content: str) -> str:
    """Wrap MAID documentation content with start and end markers.

    Args:
        content: The MAID documentation content to wrap

    Returns:
        Content wrapped with MAID section markers
    """
    return f"{MAID_SECTION_START}\n{content}\n{MAID_SECTION_END}"


def create_directories(target_dir: str) -> None:
    """Create necessary directories for MAID methodology.

    Args:
        target_dir: Target directory to initialize MAID in
    """
    manifests_dir = Path(target_dir) / "manifests"
    tests_dir = Path(target_dir) / "tests"
    maid_docs_dir = Path(target_dir) / ".maid" / "docs"

    manifests_dir.mkdir(exist_ok=True)
    print(f"✓ Created directory: {manifests_dir}")

    tests_dir.mkdir(exist_ok=True)
    print(f"✓ Created directory: {tests_dir}")

    maid_docs_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created directory: {maid_docs_dir}")


def create_example_manifest(target_dir: str) -> None:
    """Create an example manifest file to help users get started.

    NOTE: This function exists for backward compatibility with Task-031.
    As of Task-059, maid init no longer calls this function.
    Users should use 'maid snapshot' to generate manifests from existing code.

    Args:
        target_dir: Target directory containing manifests/ subdirectory
    """
    example_manifest = {
        "goal": "Example task - replace with your actual task description",
        "taskType": "create",
        "supersedes": [],
        "creatableFiles": [],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "path/to/your/file.py",
            "contains": [
                {
                    "type": "function",
                    "name": "example_function",
                    "args": [{"name": "arg1", "type": "str"}],
                    "returns": "None",
                }
            ],
        },
        "validationCommand": ["pytest", "tests/test_example.py", "-v"],
    }

    example_path = Path(target_dir) / "manifests" / "example.manifest.json"
    with open(example_path, "w") as f:
        json.dump(example_manifest, f, indent=2)

    print(f"✓ Created example manifest: {example_path}")


def copy_maid_specs(target_dir: str) -> None:
    """Copy MAID specification document to .maid/docs directory.

    Args:
        target_dir: Target directory containing .maid/docs subdirectory
    """
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent
    source_specs = maid_runner_package / "docs" / "maid_specs.md"

    if not source_specs.exists():
        print(
            f"⚠️  Warning: Could not find maid_specs.md at {source_specs}. Skipping copy."
        )
        return

    dest_specs = Path(target_dir) / ".maid" / "docs" / "maid_specs.md"
    shutil.copy2(source_specs, dest_specs)
    print(f"✓ Copied MAID specification: {dest_specs}")


def copy_unit_testing_rules(target_dir: str) -> None:
    """Copy unit testing rules document to .maid/docs directory.

    Args:
        target_dir: Target directory containing .maid/docs subdirectory
    """
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent
    source_rules = maid_runner_package / "docs" / "unit-testing-rules.md"

    if not source_rules.exists():
        print(
            f"Warning: Could not find unit-testing-rules.md at {source_rules}. "
            "Skipping copy."
        )
        return

    dest_rules = Path(target_dir) / ".maid" / "docs" / "unit-testing-rules.md"
    shutil.copy2(source_rules, dest_rules)
    print(f"Copied unit-testing-rules.md: {dest_rules}")


def _generate_maid_cli_commands() -> str:
    """Generate MAID CLI commands section (language-agnostic).

    Returns:
        String containing MAID CLI commands documentation
    """
    return """## MAID CLI Commands

**IMPORTANT: Always use the `maid` CLI for validation and snapshots, NOT direct Python scripts.**

### Whole-Codebase Validation (Recommended)

```bash
# Validate ALL active manifests with proper chaining
# Automatically excludes superseded manifests and uses manifest chain
maid validate

# Run ALL validation commands from all active manifests
# Intelligent enough to exclude inactive manifests
maid test
```

**These commands are the primary way to verify complete MAID compliance across the entire codebase.**

### Manifest Creation and Management

```bash
# Create a new manifest for a file (RECOMMENDED - auto-numbers, auto-supersedes snapshots)
maid manifest create <file-path> --goal "Description" [--artifacts JSON] [--dry-run] [--json]

# Key options for manifest create:
#   --goal "Description"          # Required: Task description
#   --artifacts JSON               # Optional: JSON array of artifact definitions
#   --task-type create|edit|refactor  # Optional: Auto-detected if not specified
#   --dry-run                      # Preview manifest without writing
#   --json                         # Output as JSON (for agent consumption)
#   --delete                       # Create deletion manifest (status: absent)
#   --rename-to <new-path>         # Create rename manifest
#   --test-file <path>             # Specify test file path
#   --readonly-files <files>       # Comma-separated readonly dependencies

# Generate a snapshot manifest from existing code
maid snapshot <file-path> [--output-dir <dir>] [--force] [--skip-test-stub]

# Generate system-wide manifest aggregating all active manifests
maid snapshot-system [--output <file>] [--manifest-dir <dir>] [--quiet]
```

### Validation Commands

```bash
# Validate a specific manifest (with optional manifest chain)
maid validate <manifest-path> [--use-manifest-chain] [--quiet]

# Validate all manifests in a directory
maid validate --manifest-dir <dir> [--use-manifest-chain]

# Validation modes
maid validate <manifest-path> --validation-mode behavioral    # Checks tests USE artifacts
maid validate <manifest-path> --validation-mode implementation  # Checks code DEFINES artifacts (default)
maid validate <manifest-path> --validation-mode schema      # Validates manifest structure only

# Important validation options:
#   --use-manifest-chain          # Merge related manifests (enables file tracking analysis)
#   --manifest-dir <dir>           # Validate all manifests in directory
#   --watch / --watch-all          # Watch mode: auto re-validate on changes
#   --coherence / --coherence-only  # Architectural coherence validation
#   --quiet, --verbose             # Control output verbosity
#   --json-output                  # Output results as JSON

# Run validation commands from manifests
maid test [--manifest-dir <dir>] [--fail-fast] [--verbose] [--quiet]

# Run tests for a single manifest
maid test --manifest <manifest-path> [--watch]

# Watch modes (Live TDD workflow)
maid test --manifest <manifest-path> --watch      # Single-manifest watch
maid test --watch-all                            # Multi-manifest watch
```

### Utility Commands

```bash
# List manifests that reference a file
maid manifests <file-path> [--manifest-dir <dir>] [--quiet] [--json-output]

# Show file tracking status (UNDECLARED/REGISTERED/TRACKED)
maid files [--manifest-dir <dir>] [--issues-only] [--status <status>] [--json]

# Generate test stubs from existing manifest
maid generate-stubs <manifest-path>

# Output the manifest JSON schema
maid schema

# Knowledge graph operations
maid graph query "<query>" [--manifest-dir <dir>]
maid graph export --format json|dot|graphml --output <file> [--manifest-dir <dir>]
maid graph analysis --type find-cycles|show-stats [--manifest-dir <dir>]
```

### Quick Reference

```bash
# Whole-Codebase Validation (Primary Commands)
maid validate     # Validate ALL active manifests with proper chaining
maid test         # Run ALL validation commands from active manifests

# Watch Mode (Live TDD workflow)
maid test --manifest manifests/task-XXX.manifest.json --watch  # Single-manifest watch
maid test --watch-all                                          # Multi-manifest watch

# Individual Task Validation Flow
# 1. During Planning: Behavioral validation (checks tests USE artifacts)
maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain

# 2. During Implementation: Implementation validation (checks code DEFINES artifacts)
maid validate manifests/task-XXX.manifest.json --validation-mode implementation --use-manifest-chain

# 3. Run actual tests
maid test --manifest manifests/task-XXX.manifest.json

# Manifest Creation Workflow
# 1. Create manifest (preferred over writing manually)
maid manifest create <file-path> --goal "Description" --dry-run  # Preview first
maid manifest create <file-path> --goal "Description"            # Create it

# 2. Validate the manifest
maid validate manifests/task-XXX.manifest.json --validation-mode behavioral

# 3. Write tests, then validate implementation
maid validate manifests/task-XXX.manifest.json --validation-mode implementation
```

### Important Concepts

**File Tracking Analysis**: When using `--use-manifest-chain` in implementation mode, MAID Runner automatically analyzes file tracking compliance:
- 🔴 **UNDECLARED**: Files not in any manifest (high priority - add to manifest)
- 🟡 **REGISTERED**: Files tracked but incomplete compliance (medium priority - add artifacts/tests)
- ✓ **TRACKED**: Files with full MAID compliance

**Watch Modes**: Enable live TDD workflow with automatic re-validation when files change. Perfect for iterative development.

**Validation Modes**:
- **Behavioral**: Verifies test files USE/CALL the declared artifacts (use during Phase 2: Planning)
- **Implementation**: Verifies code DEFINES the artifacts (use during Phase 3: Implementation)
- **Schema**: Validates manifest JSON structure only

**Manifest Creation**: Prefer `maid manifest create` over writing manifests manually. It handles:
- Auto-numbering (finds next available task number)
- Auto-supersession (unfreezes snapshotted files)
- File mode detection (creatableFiles vs editableFiles)
- Validation command generation

### Get Help

```bash
maid --help
maid validate --help
maid manifest create --help
maid snapshot --help
maid test --help
# ... and so on for any command
```"""


def _generate_validation_modes() -> str:
    """Generate validation modes section.

    Returns:
        String containing validation modes documentation
    """
    return """## Validation Modes

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)"""


def _generate_key_rules() -> str:
    """Generate key rules section.

    Returns:
        String containing key rules documentation
    """
    return """## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first → Tests → Implementation → Validate"""


def _generate_manifest_rules() -> str:
    """Generate manifest rules (CRITICAL) section.

    Returns:
        String containing manifest rules documentation
    """
    return """## Manifest Rules (CRITICAL)

**These rules are non-negotiable for maintaining MAID compliance:**

- **Manifest Immutability**: The current task's manifest (e.g., `task-050.manifest.json`) can be modified while actively working on that task. Once you move to the next task, ALL prior manifests become immutable and part of the permanent audit trail. NEVER modify completed task manifests—this breaks the chronological record of changes.

- **One File Per Manifest**: `expectedArtifacts` is an OBJECT that defines artifacts for a SINGLE file only. It is NOT an array of files. This is a common mistake that will cause validation to fail.

- **Multi-File Changes Require Multiple Manifests**: If your task modifies public APIs in multiple files (e.g., `utils.py` AND `handlers.py`), you MUST create separate sequential manifests—one per file:
  - `task-050-update-utils.manifest.json` → modifies `utils.py`
  - `task-051-update-handlers.manifest.json` → modifies `handlers.py`

- **Definition of Done (Zero Tolerance)**: A task is NOT complete until BOTH validation commands pass with ZERO errors or warnings:
  - `maid validate <manifest-path>` → Must pass 100%
  - `maid test` → Must pass 100%

  Partial completion is not acceptable. All errors must be fixed before proceeding to the next task."""


def _generate_artifact_rules() -> str:
    """Generate artifact rules section.

    Returns:
        String containing artifact rules documentation
    """
    return """## Artifact Rules

- **Public** (no `_` prefix): MUST be in manifest
- **Private** (`_` prefix): Optional in manifest
- **creatableFiles**: Strict validation (exact match)
- **editableFiles**: Permissive validation (contains at least)"""


def _generate_superseded_manifests_info() -> str:
    """Generate superseded manifests information section.

    Returns:
        String containing superseded manifests behavior documentation
    """
    return """## Superseded Manifests

**Critical:** When a manifest is superseded, it is completely excluded from MAID operations:

- `maid validate` ignores superseded manifests when merging manifest chains
- `maid test` does NOT execute `validationCommand` from superseded manifests
- Superseded manifests serve as historical documentation only—they are archived, not active"""


def _generate_snapshot_transition_pattern() -> str:
    """Generate snapshot transition pattern section.

    Returns:
        String containing snapshot transition pattern documentation
    """
    return """## Transitioning from Snapshots to Natural Evolution

**Key Insight:** Snapshot manifests are for "frozen" code. Once code evolves, transition to natural MAID flow:

1. **Snapshot Phase**: Capture complete baseline with `maid snapshot`
2. **Transition Manifest**: When file needs changes, create edit manifest that:
   - Declares ALL current functions (existing + new)
   - Supersedes the snapshot manifest
   - Uses `taskType: "edit"`
3. **Future Evolution**: Subsequent manifests only declare new changes
   - With `--use-manifest-chain`, validator merges all active manifests
   - No need to update previous manifests"""


def _generate_file_deletion_pattern() -> str:
    """Generate file deletion pattern section.

    Returns:
        String containing file deletion pattern documentation
    """
    return """## File Deletion Pattern

When removing a file tracked by MAID: Create refactor manifest → Supersede creation manifest → Delete file and tests → Validate deletion.

**Manifest**: `taskType: "refactor"`, supersedes original, `status: "absent"` in expectedArtifacts

**Validation**: File deleted, tests deleted, no remaining imports"""


def _generate_file_rename_pattern() -> str:
    """Generate file rename pattern section.

    Returns:
        String containing file rename pattern documentation
    """
    return """## File Rename Pattern

When renaming a file tracked by MAID: Create refactor manifest → Supersede creation manifest → Use `git mv` → Update manifest → Validate rename.

**Manifest**: `taskType: "refactor"`, supersedes original, new filename in `creatableFiles`, same API in `expectedArtifacts` under new location

**Validation**: Old file deleted, new file exists with working functionality, no old imports, git history preserved

**Key difference from deletion**: Rename maintains module's public API continuity under new location."""


def _generate_refactoring_flexibility() -> str:
    """Generate refactoring flexibility section.

    Returns:
        String containing refactoring flexibility documentation
    """
    return """## Refactoring Private Implementation

MAID provides flexibility for refactoring private implementation details without requiring new manifests:

- **Private code** (functions, classes, variables with `_` prefix) can be refactored freely
- **Internal logic changes** that don't affect the public API are allowed
- **Code quality improvements** (splitting functions, extracting helpers, renaming privates) are permitted

**Requirements:**
- All tests must continue to pass
- All validations must pass (`maid validate`, `maid test`)
- Public API must remain unchanged
- No MAID rules are violated

This breathing room allows practical development without bureaucracy while maintaining accountability for public interface changes."""


def _generate_additional_resources() -> str:
    """Generate additional resources section.

    Returns:
        String containing additional resources documentation
    """
    return """## Additional Resources

- **Full MAID Specification**: See `.maid/docs/maid_specs.md` for complete methodology details
- **MAID Runner Repository**: https://github.com/mamertofabian/maid-runner"""


def detect_project_language(target_dir: str) -> str:
    """Detect the primary language of the project.

    Args:
        target_dir: Target directory to analyze

    Returns:
        Language identifier: "python", "typescript", "mixed", or "unknown"
    """
    project_path = Path(target_dir)

    has_package_json = (project_path / "package.json").exists()
    has_tsconfig = (project_path / "tsconfig.json").exists()
    is_typescript = has_package_json or has_tsconfig

    has_pyproject = (project_path / "pyproject.toml").exists()
    has_setup = (project_path / "setup.py").exists()
    has_requirements = (project_path / "requirements.txt").exists()
    is_python = has_pyproject or has_setup or has_requirements

    if is_typescript and is_python:
        return "mixed"
    elif is_typescript:
        return "typescript"
    elif is_python:
        return "python"
    else:
        return "unknown"


def generate_python_claude_md() -> str:
    """Generate Python-specific MAID documentation content.

    Returns:
        String containing Python-focused MAID workflow documentation
    """
    base_content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.3**

MAID is a methodology for developing software with AI assistance by explicitly declaring:
- What files can be modified for each task
- What code artifacts (functions, classes) should be created or modified
- How to validate that the changes meet requirements

This project is compatible with MAID-aware AI agents including Claude Code and other tools that understand the MAID workflow.

## Prerequisites: Installing MAID Runner

MAID Runner is a Python CLI tool that validates manifests and runs tests. Install it using one of these methods:

```bash
# Using pip
pip install maid-runner

# Using uv (recommended for Python projects)
uv add maid-runner --dev

# Using pipx (for global installation)
pipx install maid-runner
```

After installation, the `maid` command will be available in your terminal. Verify with:
```bash
maid --help
```

**Note:** If using `uv` or a virtual environment, prefix commands with your runner (e.g., `uv run maid validate ...`).

## MAID Workflow

### Phase 1: Goal Definition
Confirm the high-level goal before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft manifest (`manifests/task-XXX.manifest.json`)
2. Draft behavioral tests (`tests/test_task_XXX_*.py`)
3. Run validation: `maid validate manifests/task-XXX.manifest.json --validation-mode behavioral`
4. Refine both tests & manifest until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run behavioral validation (from `validationCommand`)
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `pytest tests/ -v`

## Manifest Template

```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "path/to/file.py",
    "contains": [
      {
        "type": "function|class|attribute",
        "name": "artifact_name",
        "class": "ParentClass",
        "args": [{"name": "arg1", "type": "str"}],
        "returns": "ReturnType"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_file.py", "-v"]
}
```

"""
    # Build content using helper functions
    sections = [
        base_content,
        _generate_maid_cli_commands(),
        _generate_validation_modes(),
        _generate_key_rules(),
        _generate_manifest_rules(),
        _generate_artifact_rules(),
        _generate_superseded_manifests_info(),
        _generate_snapshot_transition_pattern(),
        _generate_file_deletion_pattern(),
        _generate_file_rename_pattern(),
        _generate_refactoring_flexibility(),
        """## Getting Started

1. Create your first manifest (preferred: use `maid manifest create <file-path> --goal "Description"` or manually create `manifests/task-001-<description>.manifest.json`)
2. Write behavioral tests in `tests/test_task_001_*.py`
3. Validate: `maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral`
4. Implement the code
5. Run tests to verify: `maid test`""",
        _generate_additional_resources(),
    ]
    return "\n\n".join(sections)


def generate_typescript_claude_md() -> str:
    """Generate TypeScript-specific MAID documentation content.

    Returns:
        String containing TypeScript-focused MAID workflow documentation
    """
    base_content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.3**

MAID is a methodology for developing software with AI assistance by explicitly declaring:
- What files can be modified for each task
- What code artifacts (functions, classes, interfaces, types) should be created or modified
- How to validate that the changes meet requirements

This project is compatible with MAID-aware AI agents including Claude Code and other tools that understand the MAID workflow.

## Prerequisites: Installing MAID Runner

MAID Runner is a Python CLI tool that validates manifests and runs tests. Even for TypeScript/JavaScript projects, you need Python to run the `maid` CLI.

**Option 1: Using pipx (recommended - no Python project setup needed)**
```bash
pipx install maid-runner
```

**Option 2: Using pip**
```bash
pip install maid-runner
```

**Option 3: Using uv**
```bash
uv tool install maid-runner
```

After installation, verify with:
```bash
maid --help
```

**Note:** MAID Runner requires Python 3.10+. The `maid` command validates your TypeScript/JavaScript code structure against manifests.

## MAID Workflow

### Phase 1: Goal Definition
Confirm the high-level goal before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft manifest (`manifests/task-XXX.manifest.json`)
2. Draft behavioral tests (`tests/test_task_XXX_*.test.ts`)
3. Run validation: `maid validate manifests/task-XXX.manifest.json --validation-mode behavioral`
4. Refine both tests & manifest until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run behavioral validation (from `validationCommand`)
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `npm test` (or `pnpm test` / `yarn test`)

## Manifest Template

```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "path/to/file.ts",
    "contains": [
      {
        "type": "function|class|interface",
        "name": "artifactName",
        "class": "ParentClass",
        "args": [{"name": "arg1", "type": "string"}],
        "returns": "ReturnType"
      }
    ]
  },
  "validationCommand": ["npm", "test", "--", "file.test.ts"]
}
```

"""
    # Build content using helper functions
    sections = [
        base_content,
        _generate_maid_cli_commands(),
        _generate_validation_modes(),
        _generate_key_rules(),
        _generate_manifest_rules(),
        _generate_artifact_rules(),
        _generate_superseded_manifests_info(),
        _generate_snapshot_transition_pattern(),
        _generate_file_deletion_pattern(),
        _generate_file_rename_pattern(),
        _generate_refactoring_flexibility(),
        """## Getting Started

1. Create your first manifest (preferred: use `maid manifest create <file-path> --goal "Description"` or manually create `manifests/task-001-<description>.manifest.json`)
2. Write behavioral tests in `tests/test_task_001_*.test.ts`
3. Validate: `maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral`
4. Implement the code
5. Run tests to verify: `maid test`""",
        _generate_additional_resources(),
    ]
    return "\n\n".join(sections)


def generate_mixed_claude_md() -> str:
    """Generate universal MAID documentation for mixed/unknown projects.

    Returns:
        String containing MAID workflow documentation for both Python and TypeScript
    """
    base_content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.3**

MAID is a methodology for developing software with AI assistance by explicitly declaring:
- What files can be modified for each task
- What code artifacts (functions, classes, interfaces) should be created or modified
- How to validate that the changes meet requirements

This project is compatible with MAID-aware AI agents including Claude Code and other tools that understand the MAID workflow.

**Supported Languages**: Python (`.py`) and TypeScript/JavaScript (`.ts`, `.tsx`, `.js`, `.jsx`)

## Prerequisites: Installing MAID Runner

MAID Runner is a Python CLI tool that validates manifests and runs tests. Install it using one of these methods:

**Option 1: Using pipx (recommended for global installation)**
```bash
pipx install maid-runner
```

**Option 2: Using pip**
```bash
pip install maid-runner
```

**Option 3: Using uv**
```bash
# As a tool (global)
uv tool install maid-runner

# As a dev dependency (project-local)
uv add maid-runner --dev
```

After installation, verify with:
```bash
maid --help
```

**Note:** MAID Runner requires Python 3.10+. If using `uv` or a virtual environment with a project-local install, prefix commands with your runner (e.g., `uv run maid validate ...`).

## MAID Workflow

### Phase 1: Goal Definition
Confirm the high-level goal before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft manifest (`manifests/task-XXX.manifest.json`)
2. Draft behavioral tests (`tests/test_task_XXX_*.py` or `tests/test_task_XXX_*.test.ts`)
3. Run validation: `maid validate manifests/task-XXX.manifest.json --validation-mode behavioral`
4. Refine both tests & manifest until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run behavioral validation (from `validationCommand`)
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `pytest tests/ -v` or `npm test`

## Manifest Template

### Python Example
```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "path/to/file.py",
    "contains": [
      {
        "type": "function|class|attribute",
        "name": "artifact_name",
        "args": [{"name": "arg1", "type": "str"}],
        "returns": "ReturnType"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_file.py", "-v"]
}
```

### TypeScript Example
```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "path/to/file.ts",
    "contains": [
      {
        "type": "function|class|interface",
        "name": "artifactName",
        "args": [{"name": "arg1", "type": "string"}],
        "returns": "ReturnType"
      }
    ]
  },
  "validationCommand": ["npm", "test", "--", "file.test.ts"]
}
```

"""
    # Build content using helper functions
    sections = [
        base_content,
        _generate_maid_cli_commands(),
        _generate_validation_modes(),
        _generate_key_rules(),
        _generate_manifest_rules(),
        _generate_artifact_rules(),
        _generate_superseded_manifests_info(),
        _generate_snapshot_transition_pattern(),
        _generate_file_deletion_pattern(),
        _generate_file_rename_pattern(),
        _generate_refactoring_flexibility(),
        """## Getting Started

1. Create your first manifest (preferred: use `maid manifest create <file-path> --goal "Description"` or manually create `manifests/task-001-<description>.manifest.json`)
2. Write behavioral tests in `tests/test_task_001_*.py` or `tests/test_task_001_*.test.ts`
3. Validate: `maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral`
4. Implement the code
5. Run tests to verify: `maid test`""",
        _generate_additional_resources(),
    ]
    return "\n\n".join(sections)


def generate_claude_md_content(language: str) -> str:
    """Generate MAID documentation content for CLAUDE.md based on project language.

    Args:
        language: Project language ("python", "typescript", "mixed", or "unknown")

    Returns:
        String containing MAID workflow documentation wrapped with markers
    """
    if language == "python":
        raw_content = generate_python_claude_md()
    elif language == "typescript":
        raw_content = generate_typescript_claude_md()
    else:
        # For mixed and unknown, generate comprehensive documentation
        raw_content = generate_mixed_claude_md()

    return wrap_with_markers(raw_content)


def handle_claude_md(target_dir: str, force: bool) -> None:
    """Create or update CLAUDE.md file with MAID documentation.

    Detects project language and generates appropriate documentation.
    Uses marker-based section management for idempotent updates.

    Args:
        target_dir: Target directory for CLAUDE.md
        force: If True, overwrite without prompting
    """
    claude_md_path = Path(target_dir) / "CLAUDE.md"
    language = detect_project_language(target_dir)
    content = generate_claude_md_content(language)

    if not claude_md_path.exists():
        claude_md_path.write_text(content)
        print(f"✓ Created CLAUDE.md: {claude_md_path}")
        return

    existing_content = claude_md_path.read_text()

    # If markers exist, automatically replace MAID section (idempotent update)
    if has_maid_markers(existing_content):
        # Extract just the raw content without markers for replacement
        raw_maid_content = generate_python_claude_md()
        if language == "typescript":
            raw_maid_content = generate_typescript_claude_md()
        elif language not in ("python", "typescript"):
            raw_maid_content = generate_mixed_claude_md()

        updated_content = replace_maid_section(existing_content, raw_maid_content)
        claude_md_path.write_text(updated_content)
        print(f"✓ Updated MAID section in: {claude_md_path}")
        return

    if force:
        claude_md_path.write_text(content)
        print(f"✓ Overwrote CLAUDE.md: {claude_md_path}")
        return

    print(f"\n⚠️  CLAUDE.md already exists at: {claude_md_path}")
    print("\nWhat would you like to do?")
    print("  [a] Append MAID documentation to existing file")
    print("  [o] Overwrite file with MAID documentation")
    print("  [s] Skip - don't modify existing file")

    while True:
        choice = input("\nYour choice (a/o/s): ").strip().lower()
        if choice in ["a", "o", "s"]:
            break
        print("Invalid choice. Please enter 'a', 'o', or 's'.")

    if choice == "a":
        combined_content = existing_content + "\n\n" + "=" * 40 + "\n\n" + content
        claude_md_path.write_text(combined_content)
        print(f"✓ Appended MAID documentation to: {claude_md_path}")
    elif choice == "o":
        claude_md_path.write_text(content)
        print(f"✓ Overwrote CLAUDE.md: {claude_md_path}")
    else:
        print("⊘ Skipped CLAUDE.md (existing file unchanged)")


def copy_claude_agents(target_dir: str, force: bool) -> None:
    """Copy Claude Code agent files to .claude/agents/ directory.

    Args:
        target_dir: Target directory for .claude/agents/
        force: If True, copy without prompting
    """
    # Get source location from package
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent
    source_agents = maid_runner_package / "claude" / "agents"

    if not source_agents.exists():
        print(
            f"⚠️  Warning: Could not find claude/agents at {source_agents}. Skipping copy."
        )
        return

    # Prompt user if not forcing
    if not force:
        response = input("Copy Claude Code agent files (.claude/agents)? (Y/n): ")
        if response.lower() in ("n", "no"):
            print("⊘ Skipped Claude Code agent files")
            return

    # Create destination directory
    dest_agents = Path(target_dir) / ".claude" / "agents"
    dest_agents.mkdir(parents=True, exist_ok=True)

    # Load manifest and get distributable files
    manifest = load_claude_manifest()
    distributable = get_distributable_files(manifest, "agents")

    # Copy only distributable agent files
    copied_count = 0
    for filename in distributable:
        source_file = source_agents / filename
        if source_file.exists():
            shutil.copy2(source_file, dest_agents / filename)
            copied_count += 1

    print(f"✓ Copied {copied_count} Claude Code agent files to {dest_agents}")


def copy_claude_commands(target_dir: str, force: bool) -> None:
    """Copy Claude Code command files to .claude/commands/ directory.

    Args:
        target_dir: Target directory for .claude/commands/
        force: If True, copy without prompting
    """
    # Get source location from package
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent
    source_commands = maid_runner_package / "claude" / "commands"

    if not source_commands.exists():
        print(
            f"⚠️  Warning: Could not find claude/commands at {source_commands}. Skipping copy."
        )
        return

    # Prompt user if not forcing
    if not force:
        response = input("Copy Claude Code command files (.claude/commands)? (Y/n): ")
        if response.lower() in ("n", "no"):
            print("⊘ Skipped Claude Code command files")
            return

    # Create destination directory
    dest_commands = Path(target_dir) / ".claude" / "commands"
    dest_commands.mkdir(parents=True, exist_ok=True)

    # Load manifest and get distributable files
    manifest = load_claude_manifest()
    distributable = get_distributable_files(manifest, "commands")

    # Copy only distributable command files
    copied_count = 0
    for filename in distributable:
        source_file = source_commands / filename
        if source_file.exists():
            shutil.copy2(source_file, dest_commands / filename)
            copied_count += 1

    print(f"✓ Copied {copied_count} Claude Code command files to {dest_commands}")


def run_init(target_dir: str, force: bool) -> None:
    """Initialize MAID methodology in a repository.

    Args:
        target_dir: Target directory to initialize MAID in
        force: If True, overwrite files without prompting
    """
    print(f"\n{'=' * 60}")
    print("Initializing MAID Methodology")
    print(f"{'=' * 60}\n")

    create_directories(target_dir)
    copy_maid_specs(target_dir)
    copy_unit_testing_rules(target_dir)
    handle_claude_md(target_dir, force)
    copy_claude_agents(target_dir, force)
    copy_claude_commands(target_dir, force)

    print(f"\n{'=' * 60}")
    print("✓ MAID initialization complete!")
    print(f"{'=' * 60}\n")
    print("Next steps:")
    print("1. Generate a manifest from existing code: maid snapshot <file-path>")
    print(
        '2. Or create your first task manifest: maid manifest create <file-path> --goal "Description"'
    )
    print(
        "   (Alternative: manually create manifests/task-001-<description>.manifest.json)"
    )
    print("3. Write behavioral tests in tests/test_task_001_*.py")
    print(
        "4. Validate: maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral"
    )
    print("5. Implement your code")
    print("6. Run tests: maid test\n")
