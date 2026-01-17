# MAID Runner

[![PyPI version](https://badge.fury.io/py/maid-runner.svg)](https://badge.fury.io/py/maid-runner)
[![Python Version](https://img.shields.io/pypi/pyversions/maid-runner.svg)](https://pypi.org/project/maid-runner/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tool-agnostic validation framework for the Manifest-driven AI Development (MAID) methodology. MAID Runner validates that code artifacts align with their declarative manifests, ensuring architectural integrity in AI-assisted development.

📹 **[Watch the introductory video](https://youtu.be/0a9ys-F63fQ)**

## Why MAID Runner?

LLMs generate code based on statistical likelihood, optimizing for "plausibility" rather than architectural soundness. Without intervention, this leads to "AI Slop"—code that is syntactically valid but architecturally chaotic.

**MAID Runner enforces dual-constraint validation:**
- **Behavioral (Coordinate A)**: Code must pass the test suite
- **Structural (Coordinate B)**: Code must adhere to a pre-designed JSON manifest

This transforms AI from a "Junior Developer" requiring reactive code review into a "Stochastic Compiler" that translates rigid specifications into implementation details.

→ [Full philosophy documentation](docs/maid-philosophy-and-vision.md)

## Supported Languages

| Language | Extensions | Parser | Key Features |
|----------|------------|--------|--------------|
| **Python** | `.py` | AST (built-in) | Classes, functions, methods, attributes, type hints, async/await, decorators |
| **TypeScript/JS** | `.ts`, `.tsx`, `.js`, `.jsx` | tree-sitter | Classes, interfaces, type aliases, enums, namespaces, generics, JSX/TSX |
| **Svelte** | `.svelte` | tree-sitter | Components, props, exports, script blocks, reactive statements |

## Quick Start

```bash
# Install
pip install maid-runner  # or: uv pip install maid-runner

# Initialize MAID in your project
maid init

# Interactive guide
maid howto --section quickstart
```

## Installation

### Claude Code Plugin (Recommended)

```bash
/plugin marketplace add aidrivencoder/claude-plugins
/plugin install maid-runner@aidrivencoder
```

### From PyPI

```bash
pip install maid-runner      # or: uv pip install maid-runner
```

### Multi-Tool Support

```bash
maid init                    # Claude Code (default)
maid init --cursor           # Cursor IDE
maid init --windsurf         # Windsurf IDE
maid init --generic          # Generic MAID.md
maid init --all              # All tools
```

## CLI Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `maid validate <manifest>` | Validate manifest against code | `--validation-mode behavioral\|implementation`, `--use-manifest-chain`, `--watch`, `--watch-all` |
| `maid test` | Run validation commands from manifests | `--manifest <path>`, `--watch`, `--watch-all`, `--fail-fast` |
| `maid snapshot <file>` | Generate manifest from existing code | `--output-dir`, `--force` |
| `maid snapshot-system` | Aggregate all active manifests | `--output`, `--manifest-dir` |
| `maid manifests <file>` | List manifests referencing a file | `--manifest-dir`, `--quiet` |
| `maid files` | Show file tracking status | `--manifest-dir`, `--quiet` |
| `maid init` | Initialize MAID in project | `--claude`, `--cursor`, `--windsurf`, `--generic`, `--all` |
| `maid howto` | Interactive methodology guide | `--section intro\|principles\|workflow\|quickstart\|patterns\|commands\|troubleshooting` |
| `maid manifest create <file>` | Create manifest for a file | `--goal`, `--artifacts`, `--dry-run` |

**Exit codes:** `0` = success, `1` = failure. Use `--quiet` for automation.

Run `maid howto --section commands` for detailed usage and examples.

### Common Workflows

```bash
# Validate implementation (default mode)
maid validate manifests/task-013.manifest.json --use-manifest-chain

# Validate behavioral tests
maid validate manifests/task-013.manifest.json --validation-mode behavioral

# TDD watch mode (single manifest)
maid test --manifest manifests/task-013.manifest.json --watch

# Multi-manifest watch (entire codebase)
maid test --watch-all

# Run all validation commands
maid test
```

### File Tracking

When using `--use-manifest-chain`, MAID Runner reports file compliance status:

- **🔴 UNDECLARED**: Files not in any manifest (no audit trail)
- **🟡 REGISTERED**: Files tracked but incomplete (missing artifacts/tests)
- **✓ TRACKED**: Files with full MAID compliance

## Manifest Structure

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
      {"type": "class", "name": "EmailValidator"},
      {
        "type": "function",
        "name": "validate",
        "class": "EmailValidator",
        "parameters": [{"name": "email", "type": "str"}],
        "returns": "bool"
      }
    ]
  },
  "validationCommand": ["pytest", "tests/test_email_validation.py", "-v"]
}
```

### Validation Modes

| Mode | Files | Behavior |
|------|-------|----------|
| **Strict** | `creatableFiles` | Implementation must EXACTLY match `expectedArtifacts` |
| **Permissive** | `editableFiles` | Implementation must CONTAIN `expectedArtifacts` |

### Artifact Types

**Common:** `class`, `function`, `attribute`

**TypeScript-specific:** `interface`, `type`, `enum`, `namespace`

## Development Workflow

### Phase 1: Goal Definition
Define the high-level feature or bug fix.

### Phase 2: Planning Loop
1. Create manifest: `maid manifest create <file> --goal "Description"`
2. Create behavioral tests in `tests/test_task_XXX_*.py`
3. Validate: `maid validate <manifest> --validation-mode behavioral`
4. Iterate until validation passes

### Phase 3: Implementation Loop
1. Implement code per manifest
2. Validate: `maid validate <manifest> --use-manifest-chain`
3. Run tests: `maid test --manifest <manifest>`
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `maid validate` and `maid test` pass for all active manifests.

## Python API

```python
from maid_runner import (
    validate_schema,
    validate_with_ast,
    discover_related_manifests,
    generate_snapshot,
    AlignmentError,
)

# Validate a manifest
validate_schema(manifest_data, schema_path)
validate_with_ast(manifest_data, file_path, use_manifest_chain=True)

# Generate snapshot manifest
generate_snapshot("path/to/file.py", output_dir="manifests")
```

## MAID Ecosystem

| Tool | Purpose |
|------|---------|
| **[MAID Agents](https://github.com/mamertofabian/maid-agents)** | Automated workflow orchestration using Claude Code agents |
| **[MAID Runner MCP](https://github.com/mamertofabian/maid-runner-mcp)** | MCP server exposing validation to AI agents |
| **[MAID LSP](https://github.com/mamertofabian/maid-lsp)** | Language Server Protocol for real-time IDE validation |
| **[MAID for VS Code](https://github.com/mamertofabian/vscode-maid)** | VS Code/Cursor extension with manifest explorer and diagnostics |
| **[Claude Plugins](https://github.com/aidrivencoder/claude-plugins)** | Plugin marketplace including MAID Runner |

## Development Setup

```bash
# Install dependencies
uv sync
uv sync --group dev

# Run tests
uv run python -m pytest tests/ -v

# Code quality
make format      # Auto-fix formatting
make lint        # Check style
make type-check  # Type checking
```

## Project Structure

```
maid-runner/
├── docs/                    # Documentation
├── manifests/               # Task manifests (chronological)
├── tests/                   # Test suite
├── maid_runner/
│   ├── cli/                 # CLI modules
│   └── validators/          # Core validation logic
├── examples/                # Example scripts
└── .claude/                 # Claude Code configuration
```

## Testing

```bash
uv run python -m pytest tests/ -v                    # All tests
uv run python -m pytest tests/test_task_*.py -v      # Task-specific tests
maid test                                            # MAID validation commands
```

## Requirements

- Python 3.10+
- Core: `jsonschema`, `pytest`, `tree-sitter`, `tree-sitter-typescript`
- Dev: `black`, `ruff`, `mypy`

## Contributing

This project dogfoods MAID methodology. All changes require:
1. A manifest in `manifests/`
2. Behavioral tests in `tests/`
3. Passing structural validation
4. Passing behavioral tests

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md) for guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
