"""Interactive guide to MAID methodology.

This module provides the 'maid howto' command that displays an interactive
walkthrough of the MAID (Manifest-driven AI Development) methodology.
"""


def run_howto(section: str | None = None) -> None:
    """Display interactive guide to MAID methodology.

    Args:
        section: Optional section to jump to directly (intro|principles|workflow|quickstart|patterns|commands|troubleshooting)
    """
    sections = {
        "intro": _get_intro_section,
        "principles": _get_principles_section,
        "workflow": _get_workflow_section,
        "quickstart": _get_quickstart_section,
        "patterns": _get_patterns_section,
        "commands": _get_commands_section,
        "troubleshooting": _get_troubleshooting_section,
    }

    if section and section in sections:
        # Display specific section
        content = sections[section]()
        print(content)
        return

    # Display all sections interactively
    print("=" * 70)
    print("MAID Methodology - Interactive Guide")
    print("=" * 70)
    print()

    for section_name, section_func in sections.items():
        print(f"\n{'=' * 70}")
        print(f"Section: {section_name.upper()}")
        print("=" * 70)
        print()
        content = section_func()
        print(content)
        print()
        if section_name != "troubleshooting":
            input("Press Enter to continue to next section (or Ctrl+C to exit)...")

    print("\n" + "=" * 70)
    print("End of Guide")
    print("=" * 70)
    print("\nFor complete documentation, see: .maid/docs/maid_specs.md")


def _get_intro_section() -> str:
    """Get introduction section content."""
    return """# Introduction to MAID

MAID (Manifest-driven AI Development) is a methodology for developing software
with AI assistance by explicitly declaring:

- What files can be modified for each task
- What code artifacts (functions, classes) should be created or modified
- How to validate that the changes meet requirements

This project uses MAID v1.3 to ensure architectural integrity, quality, and
maintainability when working with AI development tools.

MAID addresses the core challenge of AI code generation—its tendency to produce
plausible but flawed code without architectural awareness—by shifting the
developer's role from a direct implementer to a high-level architect who
provides AI agents with perfectly isolated, testable, and explicit tasks."""


def _get_principles_section() -> str:
    """Get core principles section content."""
    return """# Core Principles

MAID is founded on five core principles:

1. **Explicitness over Implicitness**
   An AI agent's context must be explicitly defined. The agent should never
   have to guess which files to edit, what dependencies exist, or how to
   validate its work.

2. **Extreme Isolation**
   A task given to an AI agent should be as isolated as possible from the
   wider codebase at the time of its creation. This creates a temporary
   "micro-environment" for every task, minimizing cognitive load.

3. **Test-Driven Validation**
   The sole measure of an AI's success is its ability to make a predefined
   set of tests pass. The manifest is the primary contract; tests support
   implementation and verify behavior.

4. **Directed Dependency**
   The software architecture must enforce a one-way flow of dependencies from
   volatile details (frameworks, databases) inward to stable business logic,
   as defined by Clean Architecture.

5. **Verifiable Chronology**
   The current state of any module must be the verifiable result of applying
   its entire sequence of historical manifests. This ensures transparent and
   reproducible history."""


def _get_workflow_section() -> str:
    """Get workflow section content."""
    return """# MAID Workflow

The development process is broken down into distinct phases:

## Phase 1: Goal Definition (Human Architect)
Define a high-level feature or bug fix. For example: "The system needs an
endpoint to retrieve a user's profile by their ID."

## Phase 2: Planning Loop (Human Architect & Validator Tool)
Iterative refinement before implementation:

1. Draft the manifest (the primary contract)
2. Draft behavioral tests (success criteria)
3. Run structural validation: `maid validate --validation-mode behavioral`
4. Refine both manifest and tests until validation passes

## Phase 3: Implementation (Developer Agent)
Once the plan is finalized:

1. Load ONLY files from manifest (editableFiles + readonlyFiles)
2. Implement code to pass tests
3. Run validation: `maid validate --validation-mode implementation`
4. Run tests: `maid test`
5. Iterate until all tests pass

## Phase 4: Integration
Verify complete chain: `maid validate` and `maid test`"""


def _get_quickstart_section() -> str:
    """Get quick start section content."""
    return """# Quick Start Guide

## Step 1: Initialize MAID in Your Project

```bash
maid init
```

This creates:
- `manifests/` directory for task manifests
- `tests/` directory for behavioral tests
- `.maid/docs/` with MAID specification
- `CLAUDE.md` (or tool-specific rules) with methodology documentation

## Step 2: Create Your First Manifest

```bash
maid manifest create src/my_module.py --goal "Add user profile endpoint"
```

Or manually create `manifests/task-001-add-user-profile.manifest.json`

## Step 3: Write Behavioral Tests

Create `tests/test_task_001_add_user_profile.py` that tests the expected
behavior defined in your manifest.

## Step 4: Validate Planning

```bash
maid validate manifests/task-001-add-user-profile.manifest.json --validation-mode behavioral
```

This ensures your tests USE the artifacts declared in the manifest.

## Step 5: Implement Code

Write code to make the tests pass.

## Step 6: Validate Implementation

```bash
maid validate manifests/task-001-add-user-profile.manifest.json --validation-mode implementation
maid test
```

## Step 7: Refactor (Optional)

Improve code quality while maintaining all tests passing."""


def _get_patterns_section() -> str:
    """Get common patterns section content."""
    return """# Common Patterns

## Manifest Template

```json
{
  "goal": "Clear task description",
  "taskType": "create|edit|refactor",
  "supersedes": [],
  "creatableFiles": [],
  "editableFiles": [],
  "readonlyFiles": [],
  "expectedArtifacts": {
    "file": "path/to/file.py",
    "contains": [
      {
        "type": "function",
        "name": "my_function",
        "args": [{"name": "arg1", "type": "str"}],
        "returns": "str"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_file.py", "-v"]
}
```

## Key Rules

- **One File Per Manifest**: expectedArtifacts defines artifacts for ONE file only
- **Multi-File Changes**: Create separate manifests for each file
- **Manifest Immutability**: Once a task is complete, its manifest is immutable
- **Public vs Private**: Public artifacts (no `_` prefix) MUST be in manifest;
  Private artifacts are optional

## Refactoring Private Implementation

You can refactor private code (functions/classes with `_` prefix) without
creating a new manifest, as long as:
- All tests continue to pass
- Public API remains unchanged
- Validations pass"""


def _get_commands_section() -> str:
    """Get CLI commands section content."""
    return """# MAID CLI Commands

## Whole-Codebase Validation (Recommended)

```bash
maid validate    # Validate ALL active manifests
maid test        # Run ALL validation commands
```

## Manifest Management

```bash
# Create a new manifest (RECOMMENDED)
maid manifest create <file-path> --goal "Description"

# Generate snapshot from existing code
maid snapshot <file-path>

# List manifests for a file
maid manifests <file-path>
```

## Validation

```bash
# Behavioral validation (checks tests USE artifacts)
maid validate <manifest> --validation-mode behavioral

# Implementation validation (checks code DEFINES artifacts)
maid validate <manifest> --validation-mode implementation

# With manifest chain (for file tracking analysis)
maid validate <manifest> --use-manifest-chain
```

## Testing

```bash
# Run all validation commands
maid test

# Run tests for specific manifest
maid test --manifest <manifest-path>

# Watch mode (auto re-run on changes)
maid test --manifest <manifest-path> --watch
```

## Get Help

```bash
maid --help
maid validate --help
maid manifest create --help
```"""


def _get_troubleshooting_section() -> str:
    """Get troubleshooting section content."""
    return """# Troubleshooting

## Validation Fails: "Unexpected artifacts found"

This means your code has artifacts not declared in the manifest.

**Solution**: Update the manifest to include all public artifacts, or create
a new manifest if this is a new feature.

## Tests Fail: "Artifact not found in tests"

Behavioral validation checks that tests USE the declared artifacts.

**Solution**: Ensure your tests actually call/use the functions/classes
declared in the manifest.

## File Tracking Warnings

When using `--use-manifest-chain`, you may see:
- 🔴 UNDECLARED: Files not in any manifest
- 🟡 REGISTERED: Files tracked but incomplete compliance

**Solution**: Add files to manifests with proper `expectedArtifacts` and tests.

## Manifest Chain Issues

If validation fails with manifest chain, check:
1. All manifests are properly numbered (task-001, task-002, etc.)
2. No circular dependencies in supersedes
3. File paths are correct and consistent

## Common Mistakes

1. **expectedArtifacts is an array**: It's an OBJECT with "file" and "contains"
2. **Multi-file in one manifest**: Create separate manifests per file
3. **Modifying old manifests**: Only modify the current task's manifest
4. **Skipping tests**: Tests are required for behavioral validation

For more help, see: .maid/docs/maid_specs.md"""
