# MAID Runner

A tool-agnostic validation framework for the Manifest-driven AI Development (MAID) methodology. MAID Runner validates that code artifacts align with their declarative manifests, ensuring architectural integrity in AI-assisted development.

## Architecture Philosophy

**MAID Runner is a validation-only tool.** It does NOT create files, generate code, or automate development. Instead, it validates that manifests, tests, and implementations comply with MAID methodology.

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
│   MAID Runner (Validation Only)      │
│                                      │
│   Responsibilities:                  │
│   ✓ Validate manifest schema         │
│   ✓ Validate behavioral tests        │
│   ✓ Validate implementation          │
│   ✓ Validate type hints              │
│   ✓ Validate manifest chain          │
│                                      │
│   ✗ No file creation                 │
│   ✗ No code generation               │
│   ✗ Tool-agnostic design             │
└──────────────────────────────────────┘
```

## Installation

### Local Development (Editable Install)

For local development, install the package in editable mode:

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
# Validate single manifest
maid validate <manifest_path> [options]

# Validate all manifests in directory (default: manifests/)
maid validate [--manifest-dir DIR] [options]

# Options:
#   --manifest-dir DIR                            # Validate all manifests in directory
#   --validation-mode {implementation,behavioral}  # Default: implementation
#   --use-manifest-chain                          # Merge related manifests (auto-enabled for directories)
#   --quiet, -q                                    # Suppress success messages

# Exit Codes:
#   0 = Validation passed
#   1 = Validation failed
```

**Examples:**

```bash
# Validate all manifests in default directory (with automatic manifest chain)
$ maid validate
📊 Summary: 15/15 manifest(s) passed (100.0%)

# Validate all manifests in custom directory
$ maid validate --manifest-dir custom-manifests

# Validate single manifest with chain
$ maid validate manifests/task-013.manifest.json --use-manifest-chain
✓ Validation PASSED

# Validate behavioral tests USE artifacts
$ maid validate manifests/task-013.manifest.json --validation-mode behavioral
✓ Behavioral test validation PASSED

# Quiet mode for automation
$ maid validate --quiet
# Exit code 0 = success, no output
```

### 2. Test Execution

Run validation commands from manifests across all active (non-superseded) manifests:

```bash
# Run all validation commands
maid test [options]

# Run validation commands for single manifest
maid test --manifest <manifest_path> [options]

# Options:
#   --manifest-dir DIR     # Directory containing manifests (default: manifests)
#   --manifest, -m FILE    # Run tests for single manifest only
#   --fail-fast            # Stop on first failure
#   --verbose, -v          # Show detailed output
#   --quiet, -q            # Only show summary
#   --timeout SECONDS      # Command timeout (default: 300)

# Exit Codes:
#   0 = All tests passed
#   1 = One or more tests failed
```

**Examples:**

```bash
# Run all validation commands from active manifests
$ maid test
📋 task-001.manifest.json: Running 1 validation command(s)
  [1/1] pytest tests/test_task_001.py -v
    ✅ PASSED
...
📊 Summary: 29/29 validation commands passed (100.0%)

# Run validation commands for single manifest
$ maid test --manifest task-013.manifest.json

# Stop on first failure
$ maid test --fail-fast

# Show detailed output
$ maid test --verbose

# Quiet mode for CI/CD
$ maid test --quiet
📊 Summary: 29/29 validation commands passed (100.0%)
```

**Key Features:**
- Automatically skips superseded manifests
- Detects and handles local dependencies (e.g., `maid_agents` depending on local `maid-runner`)
- Normalizes paths for cross-directory execution
- Auto-detects UV projects and sets up proper Python environment

### 3. Snapshot Generation

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

def validate_all_manifests(manifest_dir: str = "manifests") -> dict:
    """Validate all manifests in directory."""
    result = subprocess.run(
        ["maid", "validate", "--manifest-dir", manifest_dir, "--quiet"],
        capture_output=True,
        text=True
    )

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "errors": result.stderr if result.returncode != 0 else None
    }

def run_tests(manifest_dir: str = "manifests") -> dict:
    """Run all validation commands from manifests."""
    result = subprocess.run(
        ["maid", "test", "--manifest-dir", manifest_dir, "--quiet"],
        capture_output=True,
        text=True
    )

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
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
else
    echo "✗ Validation failed"
    exit 1
fi

# Run all validation commands
if maid test --quiet; then
    echo "✓ All tests passed"
    exit 0
else
    echo "✗ Tests failed"
    exit 1
fi
```

**Cross-Directory Execution:**

Both `maid validate` and `maid test` work from any directory:

```bash
# Run from anywhere - automatically changes to project root
cd /tmp
maid validate --manifest-dir ~/my-project/manifests
maid test --manifest-dir ~/my-project/manifests
```

## What MAID Runner Validates

| Validation Type | What It Checks | Command |
|----------------|----------------|---------|
| **Schema** | Manifest JSON structure | `maid validate` |
| **Behavioral Tests** | Tests USE declared artifacts | `maid validate --validation-mode behavioral` |
| **Implementation** | Code DEFINES declared artifacts | `maid validate` (default) |
| **Type Hints** | Type annotations match manifest | `maid validate` (automatic) |
| **Manifest Chain** | Historical consistency | `maid validate` (auto-enabled for directories) |
| **Test Execution** | Run validation commands | `maid test` |

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

- **Classes**: `{"type": "class", "name": "ClassName", "bases": ["BaseClass"]}`
- **Functions**: `{"type": "function", "name": "function_name", "parameters": [...]}`
- **Methods**: `{"type": "function", "name": "method_name", "class": "ParentClass", "parameters": [...]}`
- **Attributes**: `{"type": "attribute", "name": "attr_name", "class": "ParentClass"}`

## MAID Methodology

This project implements the MAID (Manifest-driven AI Development) methodology, which promotes:

- **Explicitness over Implicitness**: All AI agent context is explicitly defined
- **Extreme Isolation**: Tasks are isolated from the wider codebase during creation
- **Test-Driven Validation**: The manifest is the primary contract; tests support implementation
- **Directed Dependency**: One-way dependency flow following Clean Architecture
- **Verifiable Chronology**: Current state results from sequential manifest application

For detailed methodology documentation, see `docs/maid_specs.md`.

## Development Workflow (Manual or AI-Assisted)

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
# Run all tests (pytest + validation + manifest tests)
make test

# Run pytest suite only
uv run python -m pytest tests/ -v

# Run validation commands from all manifests
uv run maid test

# Run tests for single manifest
uv run maid test --manifest manifests/task-013.manifest.json

# Validate all manifests
uv run maid validate

# Run specific task tests
uv run python -m pytest tests/test_task_022_validate_manifest_dir.py -v
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
│   │   ├── validate.py            # Validate subcommand
│   │   ├── test.py                # Test subcommand
│   │   └── snapshot.py            # Snapshot subcommand
│   ├── utils.py                   # Utility functions
│   └── validators/                # Core validation logic
│       ├── manifest_validator.py  # Main validation engine
│       ├── type_validator.py      # Type hint validation
│       └── schemas/               # JSON schemas
├── examples/                      # Example scripts
│   └── maid_runner.py             # Optional helpers (plan/run)
└── .claude/                       # Claude Code configuration
```

## Core Components

- **Manifest Validator** (`validators/manifest_validator.py`) - Schema and AST-based validation engine
- **Type Validator** (`validators/type_validator.py`) - Type hint validation
- **Manifest Schema** (`validators/schemas/manifest.schema.json`) - JSON schema defining manifest structure
- **Task Manifests** (`manifests/`) - Chronologically ordered task definitions

## Requirements

- Python 3.12+
- Dependencies managed via `uv`
- Core dependencies: `jsonschema`, `pytest`
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
