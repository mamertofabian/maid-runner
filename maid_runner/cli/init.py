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

    # Create manifests directory
    manifests_dir.mkdir(exist_ok=True)
    print(f"✓ Created directory: {manifests_dir}")

    # Create tests directory
    tests_dir.mkdir(exist_ok=True)
    print(f"✓ Created directory: {tests_dir}")

    # Create .maid/docs directory
    maid_docs_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created directory: {maid_docs_dir}")


def create_example_manifest(target_dir: str) -> None:
    """Create an example manifest file to help users get started.

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
    # Get the path to maid_specs.md in the maid-runner installation
    # The docs directory is inside the maid_runner package
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


def generate_claude_md_content() -> str:
    """Generate MAID documentation content for CLAUDE.md.

    Returns:
        String containing MAID workflow documentation
    """
    content = """# MAID Methodology

**This project uses Manifest-driven AI Development (MAID) v1.2**

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
Verify complete chain: `pytest tests/ -v` (or your test command)

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


def handle_claude_md(target_dir: str, force: bool) -> None:
    """Create or update CLAUDE.md file with MAID documentation.

    Args:
        target_dir: Target directory for CLAUDE.md
        force: If True, overwrite without prompting
    """
    claude_md_path = Path(target_dir) / "CLAUDE.md"
    content = generate_claude_md_content()

    # If file doesn't exist, just create it
    if not claude_md_path.exists():
        claude_md_path.write_text(content)
        print(f"✓ Created CLAUDE.md: {claude_md_path}")
        return

    # File exists - handle based on force flag
    if force:
        claude_md_path.write_text(content)
        print(f"✓ Overwrote CLAUDE.md: {claude_md_path}")
        return

    # Prompt user for action
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
        # Append to existing file
        existing_content = claude_md_path.read_text()
        combined_content = existing_content + "\n\n" + "=" * 40 + "\n\n" + content
        claude_md_path.write_text(combined_content)
        print(f"✓ Appended MAID documentation to: {claude_md_path}")
    elif choice == "o":
        # Overwrite
        claude_md_path.write_text(content)
        print(f"✓ Overwrote CLAUDE.md: {claude_md_path}")
    else:  # skip
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

    # Create directory structure
    create_directories(target_dir)

    # Create example manifest
    create_example_manifest(target_dir)

    # Copy MAID specification document
    copy_maid_specs(target_dir)

    # Handle CLAUDE.md
    handle_claude_md(target_dir, force)

    print(f"\n{'=' * 60}")
    print("✓ MAID initialization complete!")
    print(f"{'=' * 60}\n")
    print("Next steps:")
    print("1. Review the example manifest in manifests/example.manifest.json")
    print(
        "2. Create your first task manifest: manifests/task-001-<description>.manifest.json"
    )
    print("3. Write behavioral tests in tests/test_task_001_*.py")
    print(
        "4. Validate: maid validate manifests/task-001-<description>.manifest.json --validation-mode behavioral"
    )
    print("5. Implement your code")
    print("6. Run tests: maid test\n")
