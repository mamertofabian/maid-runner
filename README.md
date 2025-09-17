# MAID Runner

An implementation of the Manifest-driven AI Development (MAID) methodology that validates code artifacts against their declarative manifests, ensuring AI-generated code aligns with architectural specifications.

## Overview

MAID Runner provides a validation framework that enforces architectural integrity in AI-assisted development by:

- Validating JSON manifests against defined schemas
- Using AST analysis to verify expected code artifacts exist
- Supporting manifest chaining to track file evolution over time
- Ensuring strict compliance between declared and actual code interfaces

## Architecture

### Core Components

- **Manifest Validator** (`validators/manifest_validator.py`) - Schema and AST-based validation engine
- **Manifest Schema** (`validators/schemas/manifest.schema.json`) - JSON schema defining manifest structure
- **Task Manifests** (`manifests/`) - Chronologically ordered task definitions

### Key Features

- **Schema Validation**: Validates manifest JSON against predefined schemas
- **AST Analysis**: Parses Python code to verify artifact existence and compliance
- **Manifest Chaining**: Tracks file evolution through sequential manifest application
- **Strict Interface Validation**: Ensures public interfaces exactly match declarations

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev
```

## Usage

### Running Tests

```bash
# Run all tests
export PYTHONPATH=.; uv run pytest tests/ -v

# Run specific test files
export PYTHONPATH=.; uv run pytest tests/test_manifest_validator.py -v
export PYTHONPATH=.; uv run pytest tests/test_ast_validator.py -v

# Run integration tests for specific tasks
export PYTHONPATH=.; uv run pytest tests/test_task_001_integration.py -v
```

### Code Quality

```bash
# Format code
uv run black .

# Lint code
uv run ruff check .

# Fix linting issues
uv run ruff check --fix .
```

### Validation Example

```python
from validators.manifest_validator import validate_schema, validate_with_ast

# Validate manifest schema
manifest_data = {
    "goal": "Implement user authentication",
    "creatableFiles": ["src/auth.py"],
    "readonlyFiles": ["tests/test_auth.py"],
    "expectedArtifacts": {
        "file": "src/auth.py",
        "contains": [
            {"type": "function", "name": "authenticate", "parameters": ["username", "password"]}
        ]
    },
    "validationCommand": "pytest tests/test_auth.py"
}

validate_schema(manifest_data, "validators/schemas/manifest.schema.json")

# Validate artifacts exist in code
validate_with_ast(manifest_data, "src/auth.py")
```

## Manifest Structure

Task manifests define isolated units of work with explicit inputs, outputs, and validation criteria:

```json
{
  "goal": "Implement the get_user_by_id function",
  "editableFiles": ["src/repositories/user_repository.py"],
  "readonlyFiles": ["tests/test_user_repository.py"],
  "expectedArtifacts": {
    "file": "src/repositories/user_repository.py",
    "contains": [
      {
        "type": "function",
        "name": "get_user_by_id",
        "parameters": ["user_id"]
      }
    ]
  },
  "validationCommand": "pytest tests/test_user_repository.py"
}
```

### Supported Artifact Types

- **Classes**: `{"type": "class", "name": "ClassName", "base": "BaseClass"}`
- **Functions**: `{"type": "function", "name": "function_name", "parameters": ["param1", "param2"]}`
- **Attributes**: `{"type": "attribute", "name": "attr_name", "class": "ParentClass"}`

## MAID Methodology

This project implements the MAID (Manifest-driven AI Development) methodology, which promotes:

- **Explicitness over Implicitness**: All AI agent context is explicitly defined
- **Extreme Isolation**: Tasks are isolated from the wider codebase during creation
- **Test-Driven Validation**: Success is measured by predefined test passage
- **Directed Dependency**: One-way dependency flow following Clean Architecture
- **Verifiable Chronology**: Current state results from sequential manifest application

For detailed methodology documentation, see `docs/maid_specs.md`.

## Development Workflow

1. **Define Goal**: Specify high-level feature or bug fix requirements
2. **Generate Contract**: Create comprehensive test suite defining behavior
3. **Create Manifest**: Review tests and create `task-XXX.manifest.json`
4. **Implement**: AI agent implements code based on manifest specifications
5. **Validate**: Run validation commands and merge validators
6. **Integrate**: Commit completed, validated code with confidence

## Testing Strategy

Tests are organized by component:

- `test_manifest_validator.py` - Schema validation tests
- `test_ast_validator.py` - AST-based artifact validation tests
- `test_manifest_merger.py` - Manifest chain merging logic tests
- `test_task_XXX_integration.py` - End-to-end validation for each task

## Project Structure

```
maid-runner/
├── docs/                          # Documentation and specifications
├── manifests/                     # Task manifest files (chronological)
├── tests/                         # Test suite
├── validators/                    # Core validation logic
│   ├── manifest_validator.py      # Main validation engine
│   └── schemas/                   # JSON schemas
└── .claude/                       # Claude Code configuration
    ├── commands/                  # Custom commands
    └── hooks/                     # Validation hooks
```

## Requirements

- Python 3.12+
- Dependencies managed via `uv`
- Core dependencies: `jsonschema`, `pytest`
- Development dependencies: `black`, `ruff`

## License

This project implements the MAID methodology for research and development purposes.