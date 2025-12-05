# MAID Runner

[![PyPI version](https://badge.fury.io/py/maid-runner.svg)](https://badge.fury.io/py/maid-runner)
[![Python Version](https://img.shields.io/pypi/pyversions/maid-runner.svg)](https://pypi.org/project/maid-runner/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tool-agnostic validation framework for the Manifest-driven AI Development (MAID) methodology. MAID Runner validates that code artifacts align with their declarative manifests, ensuring architectural integrity in AI-assisted development.

## Introduction Video

📹 **[Watch the introductory video](https://youtu.be/0a9ys-F63fQ)** to learn about MAID Runner and the MAID methodology.

## Supported Languages

MAID Runner supports multi-language validation with production-ready parsers:

### Python
- **Extensions**: `.py`
- **Parser**: Python AST (built-in)
- **Features**: Classes, functions, methods, attributes, type hints, async/await, decorators

### TypeScript/JavaScript
- **Extensions**: `.ts`, `.tsx`, `.js`, `.jsx`
- **Parser**: tree-sitter (production-grade)
- **Features**: Classes, interfaces, type aliases, enums, namespaces, functions, methods, decorators, generics, JSX/TSX
- **Framework Support**: Angular, React, NestJS, Vue
- **Coverage**: 99.9% of TypeScript language constructs

All validation features (behavioral tests, implementation validation, snapshot generation, test stub generation) work seamlessly across both languages.

## Architecture Philosophy

**MAID Runner is a validation-first tool.** Its core purpose is to validate that manifests, tests, and implementations comply with MAID methodology. It also provides helper commands to generate manifest snapshots and test stubs from existing code, but does not generate production code or automate the development workflow itself.

MAID Runner works with any development approach—from fully manual to fully automated. See [Usage Modes](#usage-modes) for details.

```
┌──────────────────────────────────────┐
│   External Tools (Your Choice)       │
│   - Claude Code / Aider / Cursor     │
│   - Custom AI agents                 │
│   - Manual (human developers)        │
│                                      │
│   Responsibilities:                  │
│   ✓ Create manifests                 │
│   ✓ Generate behavioral tests        │
│   ✓ Implement code                   │
│   ✓ Orchestrate workflow             │
└──────────────────────────────────────┘
              │
              │ Creates files
              ▼
┌──────────────────────────────────────┐
│   MAID Runner (Validation-First)    │
│                                      │
│   Core Responsibilities:             │
│   ✓ Validate manifest schema         │
│   ✓ Validate behavioral tests        │
│   ✓ Validate implementation          │
│   ✓ Validate type hints              │
│   ✓ Validate manifest chain          │
│   ✓ Track file compliance            │
│                                      │
│   Helper Capabilities:               │
│   ✓ Generate manifest snapshots      │
│   ✓ Generate test stubs              │
│                                      │
│   Boundaries:                        │
│   ✗ No production code generation    │
│   ✗ No workflow automation           │
└──────────────────────────────────────┘
```

## Usage Modes

MAID Runner supports three development approaches, differing only in **who creates the files**:

**1. Manual Development**
- Humans write manifests, tests, and implementation
- MAID Runner validates compliance at each step
- Best for: Learning MAID, small teams, strict oversight requirements

**2. Interactive AI-Assisted**
- AI tools suggest code, humans review and approve
- MAID Runner validates during collaboration
- Tools: Claude Code CLI, Cursor, Aider, GitHub Copilot (MCP server coming soon)
- Best for: Faster iteration with human control

**3. Fully Automated**
- AI agents orchestrate entire workflow with human review checkpoints
- MAID Runner validates automatically
- Tools: Claude Code CLI (headless mode), custom AI agents, MAID Agents framework
- Best for: Large-scale development, established MAID practices

**In all modes, MAID Runner provides identical validation.** The workflow (manifest → tests → implementation → validation) remains the same regardless of who performs each step.

## Installation

### From PyPI (Recommended)

Install MAID Runner from PyPI using pip or uv:

```bash
# Using pip
pip install maid-runner

# Using uv (recommended)
uv pip install maid-runner
```

### Local Development (Editable Install)

For local development, clone the repository and install in editable mode:

```bash
# Using pip
pip install -e .

# Using uv (recommended)
uv pip install -e .
```

After installation, the `maid` command will be available:

```bash
# Check version
maid --version

# Get help
maid --help
```

### Updating

After upgrading maid-runner, re-run `maid init` to update Claude files:

```bash
pip install --upgrade maid-runner
maid init --force  # Updates .claude/ files and CLAUDE.md
```

## The MAID Ecosystem

MAID Runner provides **validation and helper utilities** for manifest-driven development. For **full workflow automation** (planning → testing → implementing → validating), check out:

**[MAID Agents](https://github.com/mamertofabian/maid-agents)** - Automated orchestration using Claude Code agents. Handles the complete development lifecycle from idea to validated implementation.

### How They Work Together

- **MAID Runner** (this tool) = Validation layer
  - Validates manifest schemas
  - Validates implementation matches contracts
  - Validates behavioral tests
  - Tool-agnostic (use with any AI tool, IDE, or manually)

- **MAID Agents** = Orchestration + execution layer
  - Automates manifest creation
  - Generates behavioral tests
  - Implements code via Claude Code
  - Uses MAID Runner for validation

Most users start with MAID Runner for validation, then add MAID Agents for full automation.

### Python API

You can also use MAID Runner as a Python library:

```python
from maid_runner import (
    validate_schema,
    validate_with_ast,
    discover_related_manifests,
    generate_snapshot,
    AlignmentError,
    __version__,
)

# Validate a manifest schema
validate_schema(manifest_data, schema_path)

# Validate implementation against manifest
validate_with_ast(manifest_data, file_path, use_manifest_chain=True)

# Generate snapshot manifest
generate_snapshot("path/to/file.py", output_dir="manifests")
```

## Core CLI Tools (For External Tools)

### 1. Manifest Validation

```bash
# Validate manifest structure and implementation
maid validate <manifest_path> [options]

# Options:
#   --validation-mode {implementation,behavioral}  # Default: implementation
#   --use-manifest-chain                          # Merge related manifests
#   --quiet, -q                                    # Suppress success messages
#   --watch, -w                                    # Watch mode (requires manifest path)
#   --watch-all                                    # Watch all manifests
#   --skip-tests                                   # Skip running validationCommand
#   --timeout SECONDS                              # Command timeout (default: 300)

# Exit Codes:
#   0 = Validation passed
#   1 = Validation failed
```

**Examples:**

```bash
# Validate implementation matches manifest
$ maid validate manifests/task-013.manifest.json
✓ Validation PASSED

# Validate behavioral tests USE artifacts
$ maid validate manifests/task-013.manifest.json --validation-mode behavioral
✓ Behavioral test validation PASSED

# Full validation with manifest chain (recommended)
$ maid validate manifests/task-013.manifest.json --use-manifest-chain
✓ Validation PASSED

# Quiet mode for automation
$ maid validate manifests/task-013.manifest.json --quiet
# Exit code 0 = success, no output
```

**File Tracking Analysis:**

When using `--use-manifest-chain` in implementation mode, MAID Runner performs automatic file tracking analysis to detect files not properly tracked in manifests:

```bash
$ maid validate manifests/task-013.manifest.json --use-manifest-chain

✓ Validation PASSED

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE TRACKING ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 UNDECLARED FILES (3 files)
  Files exist in codebase but are not tracked in any manifest

  - scripts/helper.py
    → Not found in any manifest

  Action: Add these files to creatableFiles or editableFiles

🟡 REGISTERED FILES (5 files)
  Files are tracked but not fully MAID-compliant

  - utils/config.py
    ⚠️  In editableFiles but no expectedArtifacts
    Manifests: task-010

  Action: Add expectedArtifacts and validationCommand

✓ TRACKED (42 files)
  All other source files are fully MAID-compliant

Summary: 3 UNDECLARED, 5 REGISTERED, 42 TRACKED
```

**File Status Levels:**

- **🔴 UNDECLARED**: Files not in any manifest (high priority) - no audit trail
- **🟡 REGISTERED**: Files tracked but incomplete compliance (medium priority) - missing artifacts/tests
- **✓ TRACKED**: Files with full MAID compliance - properly documented and tested

This progressive compliance system helps teams migrate existing codebases to MAID while clearly identifying accountability gaps.

**Watch Mode:**

```bash
# Watch single manifest - re-run validation on file changes
$ maid validate manifests/task-070.manifest.json --watch
👁️  Watch mode enabled for: task-070.manifest.json
👀 Watching 3 file(s) + manifest
Press Ctrl+C to stop.

📋 Running initial validation:
✓ Validation PASSED

🔔 Detected change in maid_runner/cli/validate.py
📋 Validating task-070.manifest.json
✓ Validation PASSED

# Watch all manifests - continuous validation across codebase
$ maid validate --watch-all
👁️  Multi-manifest watch mode enabled for 55 manifest(s)
👀 Watching 127 file(s)
Press Ctrl+C to stop.

# Skip test execution (validation only)
$ maid validate manifests/task-070.manifest.json --watch --skip-tests
```

### 2. Snapshot Generation

```bash
# Generate snapshot manifest from existing code
maid snapshot <file_path> [options]

# Options:
#   --output-dir DIR    # Default: manifests/
#   --force            # Overwrite without prompting

# Exit Codes:
#   0 = Snapshot created
#   1 = Error
```

**Example:**

```bash
$ maid snapshot maid_runner/validators/manifest_validator.py --force
Snapshot manifest generated successfully: manifests/task-009-snapshot-manifest_validator.manifest.json
```

### 3. System-Wide Snapshot

```bash
# Generate system-wide manifest aggregating all active manifests
maid snapshot-system [options]

# Options:
#   --output FILE           # Default: system.manifest.json
#   --manifest-dir DIR      # Default: manifests/
#   --quiet, -q            # Suppress informational output

# Exit Codes:
#   0 = Snapshot created
#   1 = Error
```

**Example:**

```bash
$ maid snapshot-system --output system.manifest.json
Discovered 48 active manifests (excluding 12 superseded)
Aggregated 16 files with artifacts
Deduplicated 54 validation commands

System manifest generated: system.manifest.json
```

**Use Cases:**
- **Knowledge Graph Construction**: Aggregate all artifacts for system-wide analysis
- **Documentation Generation**: Create comprehensive artifact catalog
- **Migration Support**: Generate baseline snapshot when adopting MAID for existing projects
- **System Validation**: Validate that generated system manifest is schema-compliant

### 4. List Manifests by File

```bash
# List all manifests that reference a file
maid manifests <file_path> [options]

# Options:
#   --manifest-dir DIR  # Default: manifests/
#   --quiet, -q         # Show minimal output (just manifest names)

# Exit Codes:
#   0 = Success (found or not found)
```

**Examples:**

```bash
# Find which manifests reference a file
$ maid manifests maid_runner/cli/main.py

Manifests referencing: maid_runner/cli/main.py
Total: 2 manifest(s)

================================================================================

✏️  EDITED BY (2 manifest(s)):
  - task-021-maid-test-command.manifest.json
  - task-029-list-manifests-command.manifest.json

================================================================================

# Quiet mode for scripting
$ maid manifests maid_runner/validators/manifest_validator.py --quiet
created: task-001-add-schema-validation.manifest.json
edited: task-002-add-ast-alignment-validation.manifest.json
edited: task-003-behavioral-validation.manifest.json
read: task-008-snapshot-generator.manifest.json
```

**Use Cases:**
- **Dependency Analysis**: Find which tasks touched a file
- **Impact Assessment**: Understand file's role in the project (created vs edited vs read)
- **Manifest Discovery**: Quickly locate relevant manifests when investigating code
- **Audit Trail**: See the complete history of changes to a file through manifests

### 5. Run Validation Commands with Watch Mode

```bash
# Run validation commands from manifests
maid test [options]

# Options:
#   --manifest-dir DIR       # Default: manifests/
#   --manifest PATH, -m PATH # Run single manifest only
#   --fail-fast              # Stop on first failure
#   --verbose, -v            # Show detailed output
#   --quiet, -q              # Show minimal output
#   --timeout SECONDS        # Command timeout (default: 300)
#   --watch, -w              # Watch mode for single manifest (requires --manifest)
#   --watch-all              # Watch all manifests and run affected tests on changes

# Exit Codes:
#   0 = All validation commands passed
#   1 = One or more validation commands failed
```

**Important:** The `maid test` command automatically excludes superseded manifests. Only active (non-superseded) manifests have their `validationCommand` executed. Superseded manifests serve as historical documentation only—their tests will not run.

**Examples:**

```bash
# Run all validation commands from all active manifests
$ maid test
📋 task-007-type-definitions-module.manifest.json: Running 1 validation command(s)
  [1/1] pytest tests/test_task_007_type_definitions_module.py -v
    ✅ PASSED
...
📊 Summary: 69/69 validation commands passed (100.0%)

# Run validation commands from a single manifest
$ maid test --manifest task-063-multi-manifest-watch-mode.manifest.json
📋 task-063-multi-manifest-watch-mode.manifest.json: Running 1 validation command(s)
  [1/1] pytest tests/test_task_063_multi_manifest_watch_mode.py -v
    ✅ PASSED

# Watch mode for single manifest (re-run on file changes)
$ maid test --manifest task-063.manifest.json --watch
👁️  Watch mode enabled. Press Ctrl+C to stop.
👀 Watching 2 file(s) from manifest

📋 Running initial validation...
  ✅ PASSED

# File change detected automatically re-runs tests...
🔔 Detected change in maid_runner/cli/test.py
📋 Re-running validation...
  ✅ PASSED

# Watch all manifests (multi-manifest watch mode)
$ maid test --watch-all
👁️  Multi-manifest watch mode enabled. Press Ctrl+C to stop.
👀 Watching 67 file(s) across 55 manifest(s)

📋 Running initial validation for all manifests:
...
📊 Summary: 69/69 validation commands passed (100.0%)

# File change detected - only runs affected manifests...
🔔 Detected change in maid_runner/cli/test.py
📋 Running validation for task-062-maid-test-watch-mode.manifest.json
  ✅ PASSED
📋 Running validation for task-063-multi-manifest-watch-mode.manifest.json
  ✅ PASSED
```

**Watch Mode Features:**
- **Single-Manifest Watch** (`--watch --manifest X`): Watches files from one manifest
  - Automatically re-runs validation commands when tracked files change
  - Ideal for focused TDD workflow on a specific task
  - Requires `watchdog` package: `pip install watchdog`

- **Multi-Manifest Watch** (`--watch-all`): Watches all active manifests
  - Intelligently runs only affected validation commands
  - Maps file changes to manifests that reference them
  - Debounces rapid changes (2-second delay)
  - Perfect for integration testing across multiple tasks

**Use Cases:**
- **TDD Workflow**: Keep tests running while developing (`--watch --manifest`)
- **Continuous Validation**: Monitor entire codebase for regressions (`--watch-all`)
- **Quick Feedback**: Get immediate test results without manual re-runs
- **Integration Testing**: Verify changes don't break dependent tasks

### 6. File Tracking Status

```bash
# Show file tracking status overview
maid files [options]

# Options:
#   --manifest-dir DIR  # Default: manifests/
#   --quiet, -q         # Show counts only

# Exit Codes:
#   0 = Success
```

**Example:**

```bash
$ maid files
📊 File Tracking Status

🔴 UNDECLARED: 3 files
🟡 REGISTERED: 7 files
✓  TRACKED: 72 files

Total: 82 files
```

Quick visibility into MAID compliance across your codebase without running full validation.

## Optional Human Helper Tools

For manual/interactive use, MAID Runner includes convenience wrappers in `examples/maid_runner.py`:

```bash
# Interactive manifest creation (optional helper)
python examples/maid_runner.py plan --goal "Add user authentication"

# Interactive validation loop (optional helper)
python examples/maid_runner.py run manifests/task-013.manifest.json
```

**These are NOT required for automation.** External AI tools should use `maid validate` directly.

## Integration with AI Tools

MAID Runner integrates seamlessly with AI development tools in all three usage modes (see [How MAID Runner Can Be Used](#how-maid-runner-can-be-used)). The examples below show how to programmatically call MAID Runner from automation scripts, AI agents, or custom tools.

### Python Integration Example

```python
import subprocess
import json
from pathlib import Path

def validate_manifest(manifest_path: str) -> dict:
    """Use MAID Runner to validate manifest."""
    result = subprocess.run(
        ["maid", "validate", manifest_path,
         "--use-manifest-chain", "--quiet"],
        capture_output=True,
        text=True
    )

    return {
        "success": result.returncode == 0,
        "errors": result.stderr if result.returncode != 0 else None
    }

# AI tool creates manifest
manifest_path = Path("manifests/task-013-email-validation.manifest.json")
manifest_path.write_text(json.dumps({
    "goal": "Add email validation",
    "taskType": "create",
    "creatableFiles": ["validators/email_validator.py"],
    "readonlyFiles": ["tests/test_email_validation.py"],
    "expectedArtifacts": {
        "file": "validators/email_validator.py",
        "contains": [
            {"type": "class", "name": "EmailValidator"},
            {"type": "function", "name": "validate", "class": "EmailValidator"}
        ]
    },
    "validationCommand": ["pytest", "tests/test_email_validation.py", "-v"]
    // Enhanced format also supported:
    // "validationCommands": [
    //   ["pytest", "tests/test_email_validation.py", "-v"],
    //   ["mypy", "validators/email_validator.py"]
    // ]
}, indent=2))

# AI tool generates tests...
# AI tool implements code...

# Validate with MAID Runner
result = validate_manifest(str(manifest_path))
if result["success"]:
    print("✓ Validation passed - ready to commit")
else:
    print(f"✗ Validation failed: {result['errors']}")
```

### Shell Integration Example

```bash
#!/bin/bash
# AI tool workflow script

MANIFEST="manifests/task-013-email-validation.manifest.json"

# AI creates manifest (not MAID Runner's job)
cat > $MANIFEST <<EOF
{
  "goal": "Add email validation",
  "taskType": "create",
  "creatableFiles": ["validators/email_validator.py"],
  "readonlyFiles": ["tests/test_email_validation.py"],
  "expectedArtifacts": {...},
  "validationCommand": ["pytest", "tests/test_email_validation.py", "-v"]
}
EOF

# AI generates tests...
# AI implements code...

# Validate with MAID Runner
if maid validate $MANIFEST --use-manifest-chain --quiet; then
    echo "✓ Validation passed"
    exit 0
else
    echo "✗ Validation failed"
    exit 1
fi
```

## What MAID Runner Validates

| Validation Type | What It Checks | Command |
|----------------|----------------|---------|
| **Schema** | Manifest JSON structure | `maid validate` |
| **Behavioral Tests** | Tests USE declared artifacts | `maid validate --validation-mode behavioral` |
| **Implementation** | Code DEFINES declared artifacts | `maid validate` (default) |
| **Type Hints** | Type annotations match manifest | `maid validate` (automatic) |
| **Manifest Chain** | Historical consistency | `maid validate --use-manifest-chain` |
| **File References** | Which manifests touch a file | `maid manifests <file_path>` |

## Development Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev

# Install package in editable mode (after initial setup)
uv pip install -e .
```

## Manifest Structure

Task manifests define isolated units of work with explicit inputs, outputs, and validation criteria:

```json
{
  "goal": "Implement email validation",
  "taskType": "create",
  "supersedes": [],
  "creatableFiles": ["validators/email_validator.py"],
  "editableFiles": [],
  "readonlyFiles": ["tests/test_email_validation.py"],
  "expectedArtifacts": {
    "file": "validators/email_validator.py",
    "contains": [
      {
        "type": "class",
        "name": "EmailValidator"
      },
      {
        "type": "function",
        "name": "validate",
        "class": "EmailValidator",
        "parameters": [
          {"name": "email", "type": "str"}
        ],
        "returns": "bool"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_email_validation.py", "-v"]
}
```

### Validation Modes

**Strict Mode (creatableFiles):**
- Implementation must EXACTLY match expectedArtifacts
- No extra public artifacts allowed
- Perfect for new files

**Permissive Mode (editableFiles):**
- Implementation must CONTAIN expectedArtifacts
- Extra public artifacts allowed
- Perfect for editing existing files

### Supported Artifact Types

#### Common (Python & TypeScript)
- **Classes**: `{"type": "class", "name": "ClassName", "bases": ["BaseClass"]}`
- **Functions**: `{"type": "function", "name": "function_name", "parameters": [...]}`
- **Methods**: `{"type": "function", "name": "method_name", "class": "ParentClass", "parameters": [...]}`
- **Attributes**: `{"type": "attribute", "name": "attr_name", "class": "ParentClass"}`

#### TypeScript-Specific
- **Interfaces**: `{"type": "interface", "name": "InterfaceName"}`
- **Type Aliases**: `{"type": "type", "name": "TypeName"}`
- **Enums**: `{"type": "enum", "name": "EnumName"}`
- **Namespaces**: `{"type": "namespace", "name": "NamespaceName"}`

## MAID Methodology

This project implements the MAID (Manifest-driven AI Development) methodology, which promotes:

- **Explicitness over Implicitness**: All AI agent context is explicitly defined
- **Extreme Isolation**: Tasks are isolated from the wider codebase during creation
- **Test-Driven Validation**: The manifest is the primary contract; tests support implementation
- **Directed Dependency**: One-way dependency flow following Clean Architecture
- **Verifiable Chronology**: Current state results from sequential manifest application

For detailed methodology documentation, see `docs/maid_specs.md`.

## Development Workflow

This workflow applies to all [usage modes](#usage-modes)—the phases remain the same regardless of who performs them.

### Phase 1: Goal Definition
Define the high-level feature or bug fix.

### Phase 2: Planning Loop
1. **Create manifest** (JSON file defining the task)
2. **Create behavioral tests** (tests that USE the expected artifacts)
3. **Validate structure**: `maid validate <manifest> --validation-mode behavioral`
4. **Iterate** until structural validation passes
5. **Commit** manifest and tests

### Phase 3: Implementation Loop
1. **Implement code** (create/modify files per manifest)
2. **Validate implementation**: `maid validate <manifest> --use-manifest-chain`
3. **Run tests**: Execute `validationCommand` from manifest
4. **Iterate** until all tests pass
5. **Commit** implementation

### Phase 4: Integration
Verify complete chain: All manifests validate successfully.

## Testing

```bash
# Run all tests
uv run python -m pytest tests/ -v

# Run validation tests
uv run python -m pytest tests/test_manifest_to_implementation_alignment.py -v

# Run specific task tests
uv run python -m pytest tests/test_task_011_implementation_loop_controller.py -v
```

## Code Quality

```bash
# Format code
make format  # or: uv run black .

# Lint code
make lint    # or: uv run ruff check .

# Type check
make type-check
```

## Git Pre-Commit Hooks

MAID Runner includes pre-commit hooks to automatically validate code quality and MAID compliance before each commit.

### Installation

```bash
# Install pre-commit framework (already in dev dependencies)
uv sync --group dev

# Install git hooks
pre-commit install
```

**Note:** If you have a global git hooks path configured (e.g., `core.hooksPath`), you may see an error. In that case, integrate pre-commit into your global hooks script or run it manually:

```bash
# Run manually before commits
pre-commit run

# Or add to your global git hooks script:
# if [ -f .pre-commit-config.yaml ]; then
#     pre-commit run
# fi
```

### What the Hooks Check

On every commit, the following checks run automatically:

1. **Code Formatting** (`black`) - Ensures consistent code style
2. **Code Linting** (`ruff`) - Catches common errors and style issues
3. **MAID Validation** (`maid validate`) - Validates all active manifests
4. **MAID Tests** (`maid test`) - Runs validation commands from manifests
5. **Claude Files Sync** (`make sync-claude`) - Syncs `.claude/` files when modified (smart detection)

### Bypassing Hooks

In exceptional cases, you can bypass hooks with:

```bash
git commit --no-verify
```

**Note:** Use sparingly. Hooks exist to prevent MAID violations and code quality issues from being committed.

### Manual Hook Execution

You can run hooks manually without committing:

```bash
# Run all hooks on staged files
pre-commit run

# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files
```

## Project Structure

```
maid-runner/
├── docs/                          # Documentation and specifications
├── manifests/                     # Task manifest files (chronological)
├── tests/                         # Test suite
├── maid_runner/                   # Main package
│   ├── __init__.py                # Package exports
│   ├── __version__.py             # Version information
│   ├── cli/                        # CLI modules
│   │   ├── main.py                # Main CLI entry point (maid command)
│   │   ├── validate.py            # Validate subcommand (with watch mode)
│   │   ├── snapshot.py            # Snapshot subcommand
│   │   ├── list_manifests.py      # Manifests subcommand
│   │   ├── files.py               # Files subcommand (tracking status)
│   │   └── test.py                # Test subcommand (with watch mode)
│   └── validators/                # Core validation logic
│       ├── manifest_validator.py  # Main validation engine
│       ├── base_validator.py      # Abstract validator interface
│       ├── python_validator.py    # Python AST validator
│       ├── typescript_validator.py # TypeScript/JavaScript validator
│       ├── type_validator.py      # Type hint validation
│       ├── file_tracker.py        # File tracking analysis
│       └── schemas/               # JSON schemas
├── examples/                      # Example scripts
│   └── maid_runner.py             # Optional helpers (plan/run)
└── .claude/                       # Claude Code configuration
```

## Core Components

- **Manifest Validator** (`validators/manifest_validator.py`) - Schema and AST-based validation engine
- **Python Validator** (`validators/python_validator.py`) - Python AST-based artifact detection
- **TypeScript Validator** (`validators/typescript_validator.py`) - tree-sitter-based TypeScript/JavaScript validation
- **Type Validator** (`validators/type_validator.py`) - Type hint validation
- **Manifest Schema** (`validators/schemas/manifest.schema.json`) - JSON schema defining manifest structure
- **Task Manifests** (`manifests/`) - Chronologically ordered task definitions

## FAQs

### Why is there no "snapshot all files" command?

MAID is designed for **incremental adoption**, not mass conversion. A bulk snapshot command would:

**Performance issues:**
- Create thousands of manifest files (e.g., 1,317 manifests for 1,317 Python files)
- Severely degrade all MAID operations (`maid validate` scans all manifests)
- Generate massive git history noise

**Philosophy mismatch:**
- Files without manifests = files not yet touched under MAID (intentional)
- Manifests should document actual development work, not create artificial coverage
- Violates MAID's explicitness and isolation principles

**How to snapshot multiple files:**

```bash
# Snapshot files incrementally as you work on them
maid snapshot path/to/file.py

# Batch snapshot a specific directory if needed
for file in src/module_to_onboard/*.py; do
  maid snapshot "$file" --force
done

# Discover which files lack manifests
maid validate  # File tracking analysis shows undeclared files
```

The file tracking analysis (via `maid validate`) identifies undeclared files without creating manifests, supporting gradual MAID adoption.

## Requirements

- Python 3.10+
- Dependencies managed via `uv`
- Core dependencies: `jsonschema`, `pytest`, `tree-sitter`, `tree-sitter-typescript`
- Development dependencies: `black`, `ruff`, `mypy`

## Exit Codes for Automation

All validation commands use standard exit codes:
- `0` = Success (validation passed)
- `1` = Failure (validation failed or error occurred)

Use `--quiet` flag to suppress success messages for clean automation.

## Contributing

This project dogfoods the MAID methodology. All changes must:
1. Have a manifest in `manifests/`
2. Have behavioral tests in `tests/`
3. Pass structural validation
4. Pass behavioral tests

See `CLAUDE.md` for development guidelines.

## License

This project implements the MAID methodology for research and development purposes.
