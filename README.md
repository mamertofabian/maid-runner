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

## Core CLI Tools (For External Tools)

### 1. Manifest Validation

```bash
# Validate manifest structure and implementation
validate_manifest.py <manifest_path> [options]

# Options:
#   --validation-mode {implementation,behavioral}  # Default: implementation
#   --use-manifest-chain                          # Merge related manifests
#   --quiet, -q                                    # Suppress success messages

# Exit Codes:
#   0 = Validation passed
#   1 = Validation failed
```

**Examples:**

```bash
# Validate implementation matches manifest
$ validate_manifest.py manifests/task-013.manifest.json
✓ Validation PASSED

# Validate behavioral tests USE artifacts
$ validate_manifest.py manifests/task-013.manifest.json --validation-mode behavioral
✓ Behavioral test validation PASSED

# Full validation with manifest chain (recommended)
$ validate_manifest.py manifests/task-013.manifest.json --use-manifest-chain
✓ Validation PASSED

# Quiet mode for automation
$ validate_manifest.py manifests/task-013.manifest.json --quiet
# Exit code 0 = success, no output
```

### 2. Snapshot Generation

```bash
# Generate snapshot manifest from existing code
generate_snapshot.py <file_path> [options]

# Options:
#   --output-dir DIR    # Default: manifests/
#   --force            # Overwrite without prompting

# Exit Codes:
#   0 = Snapshot created
#   1 = Error
```

**Example:**

```bash
$ generate_snapshot.py validators/manifest_validator.py --force
Snapshot manifest created: manifests/task-009-snapshot-manifest_validator.manifest.json
```

## Optional Human Helper Tools

For manual/interactive use, MAID Runner includes convenience wrappers:

```bash
# Interactive manifest creation (optional helper)
maid_runner.py plan --goal "Add user authentication"

# Interactive validation loop (optional helper)
maid_runner.py run manifests/task-013.manifest.json
```

**These are NOT required for automation.** External AI tools should use `validate_manifest.py` directly.

## Integration with AI Tools

### Python Integration Example

```python
import subprocess
import json
from pathlib import Path

def validate_manifest(manifest_path: str) -> dict:
    """Use MAID Runner to validate manifest."""
    result = subprocess.run(
        ["python", "validate_manifest.py", manifest_path,
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
if validate_manifest.py $MANIFEST --use-manifest-chain --quiet; then
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
| **Schema** | Manifest JSON structure | `validate_manifest.py` |
| **Behavioral Tests** | Tests USE declared artifacts | `validate_manifest.py --validation-mode behavioral` |
| **Implementation** | Code DEFINES declared artifacts | `validate_manifest.py` (default) |
| **Type Hints** | Type annotations match manifest | `validate_manifest.py` (automatic) |
| **Manifest Chain** | Historical consistency | `validate_manifest.py --use-manifest-chain` |

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev
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
3. **Validate structure**: `validate_manifest.py <manifest> --validation-mode behavioral`
4. **Iterate** until structural validation passes
5. **Commit** manifest and tests

### Phase 3: Implementation Loop
1. **Implement code** (create/modify files per manifest)
2. **Validate implementation**: `validate_manifest.py <manifest> --use-manifest-chain`
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

## Project Structure

```
maid-runner/
├── docs/                          # Documentation and specifications
├── manifests/                     # Task manifest files (chronological)
├── tests/                         # Test suite
├── validators/                    # Core validation logic
│   ├── manifest_validator.py      # Main validation engine
│   ├── type_validator.py          # Type hint validation
│   └── schemas/                   # JSON schemas
├── validate_manifest.py           # CLI: Manifest validation (CORE TOOL)
├── generate_snapshot.py           # CLI: Snapshot generation (CORE TOOL)
├── maid_runner.py                 # CLI: Optional helpers (plan/run)
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
