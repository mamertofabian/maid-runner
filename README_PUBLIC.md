# MAID Runner

**Manifest-driven AI Development Framework**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![YouTube Series](https://img.shields.io/badge/YouTube-Building%20in%20Public-red)](YOUR_YOUTUBE_PLAYLIST)

> 🚧 **This project is being built in public!** Follow the development on [YouTube](YOUR_YOUTUBE_PLAYLIST) 🚧

---

## 🎬 Building in Public

MAID Runner is an open-source validation framework being developed transparently through a YouTube video series. Watch as we build it from the ground up, episode by episode.

- 📺 **[Watch the Series](YOUR_YOUTUBE_PLAYLIST)** - New episodes every Tuesday & Friday
- 📖 **[Episode Schedule](docs/VIDEO_SERIES_ROADMAP.md)** - Full roadmap and status
- ⭐ **Star this repo** to follow along!

**Current Progress**: Tasks 001-007 complete | Building production features

---

## The Problem

AI code generation has a critical flaw: it produces **plausible but architecturally flawed code**.

Without architectural awareness, AI agents:
- Generate code that works in demos but breaks in production
- Create tightly coupled systems that resist change
- Produce implementations that drift from specifications
- Make it impossible to verify correctness before runtime

## The Solution

**MAID Runner enforces architectural integrity in AI-assisted development** through manifest-driven validation.

Instead of hoping AI "gets it right," MAID Runner:
- ✅ Validates code structure matches explicit specifications
- ✅ Ensures tests actually exercise the code they claim to test
- ✅ Tracks every change through verifiable manifest history
- ✅ Catches architectural violations before they become bugs

## Overview

MAID Runner provides a validation framework that enforces architectural integrity in AI-assisted development by:

- **Validating JSON manifests** against defined schemas
- **Using AST analysis** to verify expected code artifacts exist
- **Behavioral validation** to ensure tests actually use the code
- **Type validation** to catch signature mismatches
- **Manifest chaining** to track file evolution over time
- **Strict compliance** between declared and actual code interfaces

---

## Quick Start

### Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/maid-runner.git
cd maid-runner

# Install dependencies
uv sync

# Install development dependencies
uv sync --group dev

# Run tests to verify installation
uv run python -m pytest tests/ -v
```

### Basic Usage

```python
from validators.manifest_validator import validate_schema, validate_with_ast

# 1. Validate manifest schema
manifest_data = {
    "goal": "Implement user authentication",
    "creatableFiles": ["src/auth.py"],
    "readonlyFiles": ["tests/test_auth.py"],
    "expectedArtifacts": {
        "file": "src/auth.py",
        "contains": [
            {
                "type": "function",
                "name": "authenticate",
                "parameters": [
                    {"name": "username", "type": "str"},
                    {"name": "password", "type": "str"}
                ],
                "returns": "bool"
            }
        ]
    },
    "validationCommand": ["pytest tests/test_auth.py"]
}

validate_schema(manifest_data, "validators/schemas/manifest.schema.json")

# 2. Validate artifacts exist in code
validate_with_ast(manifest_data, "src/auth.py")
```

---

## Architecture

### Core Components

- **Manifest Validator** (`validators/manifest_validator.py`) - Schema and AST-based validation engine
- **Type System** (`validators/types.py`) - Type definitions for manifest structures
- **Manifest Schema** (`validators/schemas/manifest.schema.json`) - JSON schema defining manifest structure
- **Task Manifests** (`manifests/`) - Chronologically ordered task definitions

### Key Features

- **Schema Validation**: Validates manifest JSON against predefined schemas
- **AST Analysis**: Parses Python code to verify artifact existence and compliance
- **Behavioral Validation**: Ensures tests actually use declared artifacts
- **Type Validation**: Verifies type hints match manifest declarations
- **Manifest Chaining**: Tracks file evolution through sequential manifest application
- **Strict Interface Validation**: Ensures public interfaces exactly match declarations

---

## Manifest Structure

Task manifests define isolated units of work with explicit inputs, outputs, and validation criteria:

```json
{
  "goal": "Implement the get_user_by_id function",
  "taskType": "edit",
  "editableFiles": ["src/repositories/user_repository.py"],
  "readonlyFiles": ["tests/test_user_repository.py"],
  "expectedArtifacts": {
    "file": "src/repositories/user_repository.py",
    "contains": [
      {
        "type": "function",
        "name": "get_user_by_id",
        "parameters": [{"name": "user_id", "type": "int"}],
        "returns": "User"
      }
    ]
  },
  "validationCommand": ["pytest tests/test_user_repository.py"]
}
```

### Supported Artifact Types

- **Classes**: `{"type": "class", "name": "ClassName", "bases": ["BaseClass"]}`
- **Functions**: `{"type": "function", "name": "function_name", "parameters": [...]}`
- **Attributes**: `{"type": "attribute", "name": "attr_name", "class": "ParentClass"}`
- **Type Hints**: Full support for Python 3.12+ type syntax including unions, optionals, generics

---

## MAID Methodology

This project implements the **MAID (Manifest-driven AI Development)** methodology, which promotes:

### Five Core Principles

1. **Explicitness over Implicitness**: All AI agent context is explicitly defined
2. **Extreme Isolation**: Tasks are isolated from the wider codebase during creation
3. **Test-Driven Validation**: Success is measured by predefined test passage
4. **Directed Dependency**: One-way dependency flow following Clean Architecture
5. **Verifiable Chronology**: Current state results from sequential manifest application

### Development Workflow

1. **Define Goal**: Specify high-level feature or bug fix requirements
2. **Create Manifest**: Define goal, scope, editable/readonly files, and expected artifacts
3. **Author Behavioral Tests**: Create a test suite that verifies behavior
4. **Implement**: AI agent implements code based on manifest specifications
5. **Validate**: Run validation commands and merge validators
6. **Integrate**: Commit completed, validated code with confidence

For detailed methodology documentation, see [docs/maid_specs.md](docs/maid_specs.md).

---

## Development

### Running Tests

```bash
# Run all tests
uv run python -m pytest tests/ -v

# Run specific test files
uv run python -m pytest tests/test_validate_schema.py -v
uv run python -m pytest tests/test_ast_validator.py -v

# Run integration tests for specific tasks
uv run python -m pytest tests/test_task_001_integration.py -v

# Run with coverage
uv run python -m pytest tests/ --cov=validators --cov-report=html
```

### Code Quality

```bash
# Format code
uv run black .

# Lint code
uv run ruff check .

# Fix linting issues
uv run ruff check --fix .

# Type checking (optional)
uv run mypy validators/
```

### Testing Strategy

Tests are organized by component:

- `test_validate_schema.py` - Schema validation tests
- `test_ast_validator.py` - AST-based artifact validation tests
- `test_manifest_merger.py` - Manifest chain merging logic tests
- `test_task_XXX_integration.py` - End-to-end validation for each task
- `validators/` - Component-specific validator tests

---

## Project Structure

```
maid-runner/
├── docs/                          # Documentation and specifications
│   ├── maid_specs.md              # MAID methodology specification
│   ├── ROADMAP.md                 # Technical roadmap
│   └── VIDEO_SERIES_ROADMAP.md    # YouTube series schedule
├── manifests/                     # Task manifest files (chronological)
├── tests/                         # Test suite
│   ├── validators/                # Validator-specific tests
│   └── test_*.py                  # Integration tests
├── validators/                    # Core validation logic
│   ├── manifest_validator.py      # Main validation engine (1779 lines)
│   ├── types.py                   # Type definitions (363 lines)
│   └── schemas/                   # JSON schemas
└── .claude/                       # Claude Code configuration
    ├── commands/                  # Custom commands
    └── hooks/                     # Validation hooks
```

---

## Contributing

We welcome contributions! This is a build-in-public project - watch the videos, try the code, open issues, and send PRs.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Ways to Contribute

- 🐛 **Report bugs** via [GitHub Issues](https://github.com/YOUR_ORG/maid-runner/issues)
- 💡 **Suggest features** that would make MAID Runner more useful
- 📝 **Improve documentation** or add examples
- 🔧 **Submit PRs** to fix bugs or add features
- 🎥 **Share your experience** using MAID Runner in your projects

---

## Community

- 📺 **YouTube Series**: [Building MAID Runner from Scratch](YOUR_YOUTUBE_PLAYLIST)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/YOUR_ORG/maid-runner/discussions)
- 🐛 **Issues**: [GitHub Issues](https://github.com/YOUR_ORG/maid-runner/issues)
- 📖 **Documentation**: [Full Docs](docs/)

---

## Professional Services

Need help implementing MAID methodology at your company?

**[made](YOUR_AGENCY_LINK)** - Our agency specializes in MAID-based architecture and AI-assisted development:

- ✅ Architecture consulting for MAID adoption
- ✅ Custom implementation services
- ✅ Team training and workshops
- ✅ Fine-tuned AI agent development

[Schedule a consultation →](YOUR_AGENCY_CONTACT)

---

## Roadmap

**Current Version**: v0.5 (Pre-release)

**Completed** (Tasks 001-007):
- ✅ Schema validation
- ✅ AST-based structural validation
- ✅ Behavioral test validation
- ✅ Type validation
- ✅ Manifest chaining support

**In Progress**:
- 🔨 Systemic validator (Task-006)
- 🔨 Command executor (Task-007)
- 🔨 Coverage analyzer (Task-008)

**Coming Soon** (v1.0):
- Multi-format reporting
- CI/CD integration (pre-commit hooks, GitHub Actions)
- Unified CLI interface
- npm/PyPI distribution

See [VIDEO_SERIES_ROADMAP.md](docs/VIDEO_SERIES_ROADMAP.md) for episode-by-episode plan.

---

## Requirements

- Python 3.12+
- Dependencies managed via `uv`
- Core dependencies: `jsonschema`, `pytest`
- Development dependencies: `black`, `ruff`, `mypy`

---

## License

[MIT License](LICENSE)

Copyright (c) 2025 Codefrost

---

## Acknowledgments

This project is built in public as part of the **AI-Driven Coder** YouTube channel.

Special thanks to:
- The Claude Code team for AI-assisted development tools
- The Python AST community for excellent documentation
- Early contributors and community members

---

**⭐ Star this repo to follow the journey!**

[Watch Episode 0](EPISODE_0_LINK) | [Read the Docs](docs/) | [Join Discussions](https://github.com/YOUR_ORG/maid-runner/discussions)
