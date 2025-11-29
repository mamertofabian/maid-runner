"""Initialize MAID methodology in an existing repository.

This module provides the 'maid init' command to set up the necessary
directory structure and documentation for using MAID in a project.
"""

import json
import shutil
from pathlib import Path


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
    content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.3**

MAID is a methodology for developing software with AI assistance by explicitly declaring:
- What files can be modified for each task
- What code artifacts (functions, classes) should be created or modified
- How to validate that the changes meet requirements

This project is compatible with MAID-aware AI agents including Claude Code and other tools that understand the MAID workflow.

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

## MAID CLI Commands

```bash
# Validate a manifest
maid validate <manifest-path> [--validation-mode behavioral|implementation]

# Generate a snapshot manifest from existing code
maid snapshot <file-path> [--output-dir <dir>]

# List manifests that reference a file
maid manifests <file-path> [--manifest-dir <dir>]

# Run all validation commands
maid test [--manifest-dir <dir>]

# Get help
maid --help
```

## Validation Modes

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first → Tests → Implementation → Validate

## Artifact Rules

- **Public** (no `_` prefix): MUST be in manifest
- **Private** (`_` prefix): Optional in manifest
- **creatableFiles**: Strict validation (exact match)
- **editableFiles**: Permissive validation (contains at least)

## Getting Started

1. Create your first manifest in `manifests/task-001-<description>.manifest.json`
2. Write behavioral tests in `tests/test_task_001_*.py`
3. Validate: `maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral`
4. Implement the code
5. Run tests to verify: `maid test`

## Additional Resources

- **Full MAID Specification**: See `.maid/docs/maid_specs.md` for complete methodology details
- **MAID Runner Repository**: https://github.com/mamertofabian/maid-runner
"""
    return content


def generate_typescript_claude_md() -> str:
    """Generate TypeScript-specific MAID documentation content.

    Returns:
        String containing TypeScript-focused MAID workflow documentation
    """
    content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.3**

MAID is a methodology for developing software with AI assistance by explicitly declaring:
- What files can be modified for each task
- What code artifacts (functions, classes, interfaces, types) should be created or modified
- How to validate that the changes meet requirements

This project is compatible with MAID-aware AI agents including Claude Code and other tools that understand the MAID workflow.

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

## MAID CLI Commands

```bash
# Validate a manifest
maid validate <manifest-path> [--validation-mode behavioral|implementation]

# Generate a snapshot manifest from existing code
maid snapshot <file-path> [--output-dir <dir>]

# List manifests that reference a file
maid manifests <file-path> [--manifest-dir <dir>]

# Run all validation commands
maid test [--manifest-dir <dir>]

# Get help
maid --help
```

## Validation Modes

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first → Tests → Implementation → Validate

## Artifact Rules

- **Public** (no `_` prefix): MUST be in manifest
- **Private** (`_` prefix): Optional in manifest
- **creatableFiles**: Strict validation (exact match)
- **editableFiles**: Permissive validation (contains at least)

## Getting Started

1. Create your first manifest in `manifests/task-001-<description>.manifest.json`
2. Write behavioral tests in `tests/test_task_001_*.test.ts`
3. Validate: `maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral`
4. Implement the code
5. Run tests to verify: `maid test`

## Additional Resources

- **Full MAID Specification**: See `.maid/docs/maid_specs.md` for complete methodology details
- **MAID Runner Repository**: https://github.com/mamertofabian/maid-runner
"""
    return content


def generate_mixed_claude_md() -> str:
    """Generate universal MAID documentation for mixed/unknown projects.

    Returns:
        String containing MAID workflow documentation for both Python and TypeScript
    """
    content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.3**

MAID is a methodology for developing software with AI assistance by explicitly declaring:
- What files can be modified for each task
- What code artifacts (functions, classes, interfaces) should be created or modified
- How to validate that the changes meet requirements

This project is compatible with MAID-aware AI agents including Claude Code and other tools that understand the MAID workflow.

**Supported Languages**: Python (`.py`) and TypeScript/JavaScript (`.ts`, `.tsx`, `.js`, `.jsx`)

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

## MAID CLI Commands

```bash
# Validate a manifest
maid validate <manifest-path> [--validation-mode behavioral|implementation]

# Generate a snapshot manifest from existing code
maid snapshot <file-path> [--output-dir <dir>]

# List manifests that reference a file
maid manifests <file-path> [--manifest-dir <dir>]

# Run all validation commands
maid test [--manifest-dir <dir>]

# Get help
maid --help
```

## Validation Modes

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first → Tests → Implementation → Validate

## Artifact Rules

- **Public** (no `_` prefix): MUST be in manifest
- **Private** (`_` prefix): Optional in manifest
- **creatableFiles**: Strict validation (exact match)
- **editableFiles**: Permissive validation (contains at least)

## Getting Started

1. Create your first manifest in `manifests/task-001-<description>.manifest.json`
2. Write behavioral tests in `tests/test_task_001_*.py` or `tests/test_task_001_*.test.ts`
3. Validate: `maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral`
4. Implement the code
5. Run tests to verify: `maid test`

## Additional Resources

- **Full MAID Specification**: See `.maid/docs/maid_specs.md` for complete methodology details
- **MAID Runner Repository**: https://github.com/mamertofabian/maid-runner
"""
    return content


def generate_claude_md_content(language: str) -> str:
    """Generate MAID documentation content for CLAUDE.md based on project language.

    Args:
        language: Project language ("python", "typescript", "mixed", or "unknown")

    Returns:
        String containing MAID workflow documentation
    """
    if language == "python":
        return generate_python_claude_md()
    elif language == "typescript":
        return generate_typescript_claude_md()
    else:
        # For mixed and unknown, generate comprehensive documentation
        return generate_mixed_claude_md()


def handle_claude_md(target_dir: str, force: bool) -> None:
    """Create or update CLAUDE.md file with MAID documentation.

    Detects project language and generates appropriate documentation.

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
        existing_content = claude_md_path.read_text()
        combined_content = existing_content + "\n\n" + "=" * 40 + "\n\n" + content
        claude_md_path.write_text(combined_content)
        print(f"✓ Appended MAID documentation to: {claude_md_path}")
    elif choice == "o":
        claude_md_path.write_text(content)
        print(f"✓ Overwrote CLAUDE.md: {claude_md_path}")
    else:
        print("⊘ Skipped CLAUDE.md (existing file unchanged)")


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
    handle_claude_md(target_dir, force)

    print(f"\n{'=' * 60}")
    print("✓ MAID initialization complete!")
    print(f"{'=' * 60}\n")
    print("Next steps:")
    print("1. Generate a manifest from existing code: maid snapshot <file-path>")
    print(
        "2. Or create your first task manifest: manifests/task-001-<description>.manifest.json"
    )
    print("3. Write behavioral tests in tests/test_task_001_*.py")
    print(
        "4. Validate: maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral"
    )
    print("5. Implement your code")
    print("6. Run tests: maid test\n")
