# MAID Runner

[![PyPI version](https://badge.fury.io/py/maid-runner.svg)](https://badge.fury.io/py/maid-runner)
[![Python Version](https://img.shields.io/pypi/pyversions/maid-runner.svg)](https://pypi.org/project/maid-runner/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tool-agnostic validation framework and Python library for the Manifest-driven AI Development (MAID) methodology. MAID Runner validates that code artifacts align with declarative YAML manifests, ensuring architectural integrity in AI-assisted development. Integrates with [ArchSpec](https://archspec.dev) for spec-to-code pipelines.

**[Watch the introductory video](https://youtu.be/0a9ys-F63fQ)**

> [Full AI Compiler workflow guide](docs/ai-compiler-workflow.md)

## Why MAID Runner?

LLMs generate code based on statistical likelihood, optimizing for "plausibility" rather than architectural soundness. Without intervention, this leads to "AI Slop" -- code that is syntactically valid but architecturally chaotic.

**MAID Runner enforces three-stream validation:**
- **Acceptance (WHAT)**: Immutable tests from specifications define system behavior
- **Structural (SKELETON)**: AST-level verification that code matches manifest contracts
- **Unit (HOW)**: Implementation-level tests verify internal correctness

This transforms AI from a "Junior Developer" requiring reactive code review into a "Stochastic Compiler" that translates rigid specifications into implementation details.

> [Full philosophy documentation](docs/maid-philosophy-and-vision.md)

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
pip install maid-runner              # Python only (core — no tree-sitter)
pip install maid-runner[all]         # All language support (TypeScript, Svelte)
pip install maid-runner[typescript]  # TypeScript/JS only
pip install maid-runner[watch]       # File watching for TDD mode
```

### Multi-Tool Support

```bash
maid init                        # Claude Code (default)
maid init --tool cursor          # Cursor IDE
maid init --tool windsurf        # Windsurf IDE
maid init --tool generic         # Generic MAID.md
```

## CLI Reference

| Command | Purpose | Key Options |
|---------|---------|-------------|
| `maid validate [manifest]` | Validate manifest against code | `--mode behavioral\|implementation`, `--no-chain`, `--coherence`, `--json`, `--watch`, `--watch-all` |
| `maid test` | Run validation commands from manifests | `--manifest <path>`, `--watch`, `--watch-all`, `--fail-fast`, `--json` |
| `maid snapshot <file>` | Generate manifest from existing code | `--output-dir`, `--force` |
| `maid snapshot-system` | Aggregate all active manifests | `--output`, `--manifest-dir` |
| `maid manifests <file>` | List manifests referencing a file | `--manifest-dir`, `--quiet` |
| `maid files` | Show file tracking status | `--manifest-dir`, `--quiet` |
| `maid graph` | Knowledge graph operations | `query`, `export`, `analyze` |
| `maid coherence` | Run coherence checks | `--checks`, `--exclude`, `--json` |
| `maid schema` | Display manifest JSON Schema | |
| `maid init` | Initialize MAID in project | `--tool claude\|cursor\|windsurf\|generic\|auto` |
| `maid howto` | Interactive methodology guide | `--section intro\|principles\|workflow\|quickstart\|patterns\|commands\|troubleshooting` |
| `maid manifest create <file>` | Create manifest for a file | `--goal`, `--artifacts`, `--dry-run` |
| `maid chain log` | Show manifest event log | `--until-seq N`, `--version-tag TAG`, `--active`, `--json` |
| `maid chain replay` | Preview effective artifacts at a point in time | `--until-seq N`, `--version-tag TAG`, `--json` |

**Exit codes:** `0` = success, `1` = validation failure, `2` = usage error. Use `--quiet` for automation.

Run `maid howto --section commands` for detailed usage and examples.

### Common Workflows

```bash
# Validate all manifests (chains enabled by default)
maid validate

# Validate a single manifest
maid validate manifests/add-auth.manifest.yaml

# Validate without chain merging
maid validate manifests/add-auth.manifest.yaml --no-chain

# Validate behavioral tests
maid validate manifests/add-auth.manifest.yaml --mode behavioral

# Validate with coherence checks
maid validate --coherence

# TDD watch mode (single manifest)
maid test --manifest manifests/add-auth.manifest.yaml --watch

# Multi-manifest watch (entire codebase)
maid test --watch-all

# Run all validation commands
maid test

# JSON output for CI/CD
maid validate --json
```

### File Tracking

When validating with manifest chains (default), MAID Runner reports file compliance status:

- **UNDECLARED**: Files not in any manifest (no audit trail)
- **REGISTERED**: Files tracked but incomplete (missing artifacts/tests)
- **TRACKED**: Files with full MAID compliance

## Manifest Structure (v2 YAML)

```yaml
schema: "2"
goal: "Implement email validation"
type: feature
files:
  create:
    - path: validators/email_validator.py
      artifacts:
        - kind: class
          name: EmailValidator
        - kind: method
          name: validate
          of: EmailValidator
          args:
            - name: email
              type: str
          returns: bool
  read:
    - tests/test_email_validation.py
validate:
  - pytest tests/test_email_validation.py -v
```

V1 JSON manifests are auto-converted when loaded.

### Validation Modes

| Mode | Files | Behavior |
|------|-------|----------|
| **Strict** | `files.create` | Implementation must EXACTLY match declared artifacts |
| **Permissive** | `files.edit` | Implementation must CONTAIN declared artifacts |

### Artifact Kinds

**Common:** `class`, `function`, `method`, `attribute`

**TypeScript-specific:** `interface`, `type`, `enum`, `namespace`

### Manifest Event Log

MAID Runner v2.4.0 introduces an event-log system for tracking manifest history:

```yaml
schema: "2"
goal: "Add user authentication"
type: feature
sequence_number: 42         # optional — deterministic ordering
version_tag: "v2.4.0"       # optional — release label
```

**Inspect the event log:**
```bash
maid chain log                    # Full history (includes superseded)
maid chain log --until-seq 10     # Up to sequence 10
maid chain log --version-tag v2.4.0 --json
maid chain log --active           # Active manifests only
```

**Preview artifact state at a point in time:**
```bash
maid chain replay --until-seq 10 --json
maid chain replay --version-tag v2.4.0
```

The event log provides deterministic ordering via `sequence_number` (falls back to `created`), includes superseded manifests in the historical record, and supports point-in-time queries through `event_log_until()` and `replay_until()` APIs.

## Development Workflow

### Phase 1: Goal Definition
Define the high-level feature or bug fix.

### Phase 2: Planning Loop
1. Create manifest: `maid manifest create <file> --goal "Description"`
2. Create behavioral tests in `tests/`
3. Validate: `maid validate <manifest> --mode behavioral`
4. Iterate until validation passes

### Phase 3: Implementation Loop
1. Implement code per manifest
2. Validate: `maid validate <manifest>`
3. Run tests: `maid test --manifest <manifest>`
4. Iterate until all tests pass

### Phase 4: Integration
Verify complete chain: `maid validate` and `maid test` pass for all active manifests.

## Library API

MAID Runner provides a Python library API for direct integration with tools, CI/CD, and custom scripts.

### Basic Validation

```python
from maid_runner import validate, validate_all

# Validate a single manifest
result = validate("manifests/add-auth.manifest.yaml")
if result.success:
    print("All checks passed")
else:
    for error in result.errors:
        print(f"{error.code.value}: {error.message}")

# Validate all manifests in directory
batch = validate_all("manifests/")
print(f"{batch.passed}/{batch.total_manifests} passed")
```

### Manifest Chain Operations

```python
from maid_runner import ManifestChain

chain = ManifestChain("manifests/")

for m in chain.active_manifests():
    print(f"{m.slug}: {m.goal}")

artifacts = chain.merged_artifacts_for("src/auth/service.py")
```

### Loading and Saving Manifests

```python
from maid_runner import load_manifest, save_manifest

manifest = load_manifest("manifests/add-auth.manifest.yaml")  # YAML v2 or JSON v1
print(manifest.goal)
save_manifest(manifest, "manifests/copy.manifest.yaml")
```

### Snapshot Generation

```python
from maid_runner import generate_snapshot

manifest = generate_snapshot("src/auth/service.py")
print(f"Found {len(manifest.all_file_specs[0].artifacts)} artifacts")
```

### JSON Output for Tool Integration

```python
from maid_runner import validate

result = validate("manifests/add-auth.manifest.yaml")
print(result.to_json())  # Structured JSON output
```

### Custom Validator Registration

```python
from maid_runner import ValidatorRegistry, BaseValidator, CollectionResult

class GoValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls):
        return (".go",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

ValidatorRegistry.register(GoValidator)
```

## MAID Ecosystem

| Tool | Purpose |
|------|---------|
| **[MAID Agents](https://github.com/mamertofabian/maid-agents)** | Automated workflow orchestration using Claude Code agents |
| **[MAID Runner MCP](https://github.com/mamertofabian/maid-runner-mcp)** | MCP server exposing validation to AI agents |
| **[MAID LSP](https://github.com/mamertofabian/maid-lsp)** | Language Server Protocol for real-time IDE validation |
| **[MAID for VS Code](https://github.com/mamertofabian/vscode-maid)** | VS Code/Cursor extension with manifest explorer and diagnostics |
| **[Claude Plugins](https://github.com/aidrivencoder/claude-plugins)** | Plugin marketplace including MAID Runner |
| **[ArchSpec](https://archspec.dev)** | AI-powered spec generation with MAID manifest export |

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
├── manifests/               # Task manifests (YAML v2)
├── tests/
│   ├── core/                # Core module tests
│   ├── validators/          # Validator tests
│   ├── coherence/           # Coherence check tests
│   ├── graph/               # Knowledge graph tests
│   ├── compat/              # Compatibility tests
│   ├── cli/                 # CLI tests
│   ├── integration/         # Integration tests
│   └── e2e/                 # End-to-end tests
├── maid_runner/
│   ├── core/                # Manifest loading, validation, chain, types
│   ├── validators/          # Language-specific artifact collectors
│   ├── graph/               # Knowledge graph (manifest relationships)
│   ├── coherence/           # Architectural coherence checks
│   ├── compat/              # V1 JSON backward compatibility
│   ├── cli/commands/        # CLI command modules
│   └── schemas/             # JSON Schema (v1, v2)
├── examples/                # Example scripts
└── .claude/                 # Claude Code configuration
```

## Testing

```bash
uv run python -m pytest tests/ -v                    # All tests
uv run python -m pytest tests/core/ -v               # Core tests
uv run python -m pytest tests/validators/ -v          # Validator tests
maid test                                            # MAID validation commands
```

## Requirements

- Python 3.10+
- Core: `jsonschema`, `pyyaml`
- Optional: `tree-sitter`, `tree-sitter-typescript` (TypeScript/JS support), `tree-sitter-svelte` (Svelte support)
- Dev: `black`, `ruff`, `mypy`, `pytest`

## Contributing

This project dogfoods MAID methodology. All changes require:
1. A manifest in `manifests/`
2. Behavioral tests in `tests/`
3. Passing structural validation
4. Passing behavioral tests

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md) for guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
