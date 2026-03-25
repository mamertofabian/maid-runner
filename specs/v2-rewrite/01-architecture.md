# MAID Runner v2 - Architecture

**References:** [00-overview.md](00-overview.md)

## Package Structure

```
maid-runner/
├── maid_runner/
│   ├── __init__.py                    # Public API re-exports (see 10-public-api.md)
│   ├── __version__.py                 # Version string
│   │
│   ├── core/                          # Foundation - zero optional deps
│   │   ├── __init__.py                # Re-exports core public API
│   │   ├── manifest.py                # Manifest loading, parsing, schema validation
│   │   ├── chain.py                   # ManifestChain: resolution, merge, supersession
│   │   ├── validate.py                # ValidationEngine: orchestrates all validation
│   │   ├── result.py                  # ValidationResult, ValidationError, ErrorCode
│   │   ├── snapshot.py                # Snapshot generation (delegates to validators)
│   │   ├── config.py                  # MaidConfig: project-level configuration
│   │   └── types.py                   # Shared type definitions (Artifact, FileSpec, etc.)
│   │
│   ├── validators/                    # Language-specific AST analysis
│   │   ├── __init__.py                # ValidatorRegistry, get_validator()
│   │   ├── base.py                    # BaseValidator ABC
│   │   ├── python.py                  # PythonValidator (stdlib ast - always available)
│   │   ├── typescript.py              # TypeScriptValidator (tree-sitter - optional)
│   │   └── svelte.py                  # SvelteValidator (tree-sitter - optional)
│   │
│   ├── graph/                         # Knowledge graph (optional feature)
│   │   ├── __init__.py                # Re-exports: KnowledgeGraph, GraphBuilder, etc.
│   │   ├── model.py                   # Node types, Edge types, KnowledgeGraph container
│   │   ├── builder.py                 # GraphBuilder: manifests -> graph
│   │   ├── query.py                   # GraphQuery: traversal, search, analysis
│   │   └── export.py                  # Exporters: JSON, DOT, GraphML
│   │
│   ├── coherence/                     # Architectural coherence (optional feature)
│   │   ├── __init__.py                # Re-exports: CoherenceEngine, etc.
│   │   ├── engine.py                  # CoherenceEngine: runs all checks
│   │   ├── result.py                  # CoherenceResult, CoherenceIssue, IssueSeverity
│   │   └── checks/                    # Individual check implementations
│   │       ├── __init__.py            # Check registry
│   │       ├── base.py                # BaseCheck ABC
│   │       ├── duplicate.py           # Duplicate artifact detection
│   │       ├── signature.py           # Signature conflict detection
│   │       ├── boundary.py            # Module boundary violations
│   │       ├── naming.py              # Naming convention checks
│   │       ├── dependency.py          # Dependency availability
│   │       ├── pattern.py             # Pattern consistency
│   │       └── constraint.py          # Architectural constraints
│   │
│   ├── compat/                        # V1 backward compatibility
│   │   ├── __init__.py
│   │   └── v1_loader.py              # Load and convert v1 JSON manifests to v2 format
│   │
│   ├── cli/                           # Thin CLI layer
│   │   ├── __init__.py
│   │   ├── main.py                    # Entry point, argument parsing, subcommand routing
│   │   ├── commands/                  # One file per command
│   │   │   ├── __init__.py
│   │   │   ├── validate.py            # maid validate
│   │   │   ├── test.py                # maid test
│   │   │   ├── snapshot.py            # maid snapshot / maid snapshot-system
│   │   │   ├── init.py                # maid init
│   │   │   ├── manifest.py            # maid manifest create
│   │   │   ├── files.py               # maid files / maid manifests
│   │   │   ├── graph.py               # maid graph
│   │   │   ├── coherence.py           # maid coherence (also integrated into validate)
│   │   │   ├── schema.py              # maid schema
│   │   │   └── howto.py               # maid howto
│   │   └── format.py                  # Output formatters (text, JSON, LSP-compatible)
│   │
│   └── schemas/                       # JSON/YAML schema files
│       ├── manifest.v2.schema.json    # V2 manifest JSON Schema (for validation)
│       └── manifest.v1.schema.json    # V1 manifest JSON Schema (for compat)
│
├── tests/                             # Domain-organized tests
│   ├── conftest.py                    # Shared fixtures
│   ├── core/
│   │   ├── test_manifest.py
│   │   ├── test_chain.py
│   │   ├── test_validate.py
│   │   ├── test_result.py
│   │   ├── test_snapshot.py
│   │   └── test_config.py
│   ├── validators/
│   │   ├── test_registry.py
│   │   ├── test_python.py
│   │   ├── test_typescript.py
│   │   └── test_svelte.py
│   ├── graph/
│   │   ├── test_model.py
│   │   ├── test_builder.py
│   │   ├── test_query.py
│   │   └── test_export.py
│   ├── coherence/
│   │   ├── test_engine.py
│   │   └── test_checks.py
│   ├── compat/
│   │   └── test_v1_loader.py
│   ├── cli/
│   │   ├── test_validate_cmd.py
│   │   ├── test_test_cmd.py
│   │   ├── test_snapshot_cmd.py
│   │   └── test_init_cmd.py
│   └── integration/
│       ├── test_full_workflow.py
│       └── test_library_api.py
│
├── manifests/                         # Project's own manifests (YAML v2 format)
├── specs/                             # This specification directory
├── docs/
│   ├── maid_specs.md
│   └── unit-testing-rules.md
├── pyproject.toml
├── Makefile
└── README.md
```

## Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLI Layer                          │
│   cli/main.py + cli/commands/*.py + cli/format.py   │
│   ~500 lines total. Argument parsing and output      │
│   formatting ONLY. No business logic.                │
├─────────────────────────────────────────────────────┤
│                  Public API Layer                     │
│   maid_runner/__init__.py                            │
│   Re-exports: validate(), snapshot(), ManifestChain  │
│   This is what ecosystem tools import.               │
├─────────────────────────────────────────────────────┤
│                   Core Layer                          │
│   core/validate.py    core/manifest.py               │
│   core/chain.py       core/snapshot.py               │
│   core/result.py      core/types.py                  │
│   All orchestration and business logic.              │
│   Zero optional dependencies.                        │
├─────────────────────────────────────────────────────┤
│              Validator Plugin Layer                   │
│   validators/base.py (ABC)                           │
│   validators/python.py (always available)            │
│   validators/typescript.py (optional: tree-sitter)   │
│   validators/svelte.py (optional: tree-sitter)       │
├─────────────────────────────────────────────────────┤
│             Optional Feature Modules                 │
│   graph/ (knowledge graph)                           │
│   coherence/ (architectural checks)                  │
│   compat/ (v1 backward compatibility)                │
└─────────────────────────────────────────────────────┘
```

## Module Dependency Rules

### Allowed Dependencies (Top-Down)

```
cli/ ──────────> core/, validators/, graph/, coherence/, compat/
core/ ─────────> validators/ (via registry interface only)
graph/ ────────> core/ (reads manifests, types)
coherence/ ───> core/ (reads manifests, types), graph/ (uses knowledge graph)
compat/ ──────> core/ (converts to v2 types)
validators/ ──> (nothing from maid_runner — self-contained)
```

### Forbidden Dependencies

```
core/ ──X──> cli/           # Core MUST NOT import CLI
core/ ──X──> graph/         # Core MUST NOT depend on optional features
core/ ──X──> coherence/     # Core MUST NOT depend on optional features
validators/ ──X──> core/    # Validators MUST NOT import core
validators/ ──X──> cli/     # Validators MUST NOT import CLI
graph/ ──X──> cli/          # Features MUST NOT import CLI
coherence/ ──X──> cli/      # Features MUST NOT import CLI
```

### Why Validators Don't Import Core

Validators receive data (source code string, file path) and return data (list of found artifacts). They don't need to know about manifests, chains, or validation logic. This keeps them independently testable and pluggable.

## Data Flow

### Validation Flow

```
User calls: validate(manifest_path, mode="implementation")
       │
       ▼
┌─ core/manifest.py ─────────────────────────┐
│  load_manifest(path)                        │
│  - Detects format (YAML v2 or JSON v1)      │
│  - If v1: delegates to compat/v1_loader.py  │
│  - Schema validates against manifest.v2     │
│  - Returns: Manifest dataclass              │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─ core/chain.py ─────────────────────────────┐
│  ManifestChain(manifest_dir)                │
│  - Discovers all manifests in directory      │
│  - Resolves supersession graph               │
│  - Computes active manifests                 │
│  - Merges artifacts per file                 │
│  - Returns: merged file->artifacts mapping   │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─ core/validate.py ──────────────────────────┐
│  ValidationEngine.validate(manifest, chain) │
│  - For each file in manifest.files:         │
│    - Gets validator from registry            │
│    - Behavioral mode: check tests USE arts   │
│    - Implementation mode: check code DEFINES │
│    - Type validation (args, returns)         │
│    - Strict vs permissive enforcement        │
│  - File tracking analysis                    │
│  - Aggregates into ValidationResult          │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─ core/result.py ────────────────────────────┐
│  ValidationResult                           │
│  - success: bool                             │
│  - errors: list[ValidationError]             │
│  - warnings: list[ValidationError]           │
│  - file_tracking: FileTrackingReport         │
│  - to_json() / to_text() / to_lsp()         │
└─────────────────────────────────────────────┘
```

### Snapshot Flow

```
User calls: snapshot(file_path)
       │
       ▼
┌─ core/snapshot.py ──────────────────────────┐
│  generate_snapshot(file_path)               │
│  - Detects language from extension           │
│  - Gets validator from registry              │
│  - Calls validator.collect_artifacts()       │
│  - Builds Manifest dataclass                 │
│  - Generates test stub                       │
│  - Returns: Manifest (saveable to YAML)      │
└─────────────────────────────────────────────┘
```

### Graph Flow

```
User calls: build_graph(manifest_dir)
       │
       ▼
┌─ graph/builder.py ──────────────────────────┐
│  GraphBuilder.build(manifest_dir)           │
│  - Loads all active manifests via core/chain │
│  - Creates nodes (manifest, file, artifact)  │
│  - Creates edges (supersedes, creates, etc.) │
│  - Returns: KnowledgeGraph                   │
└─────────────────────────────────────────────┘
       │
       ▼
┌─ graph/query.py ────────────────────────────┐
│  GraphQuery(graph)                          │
│  - find_node(), get_neighbors()              │
│  - find_cycles(), dependency_analysis()      │
│  - impact_analysis(), find_definitions()     │
└─────────────────────────────────────────────┘
```

## Configuration

### pyproject.toml (Distribution)

```toml
[project]
name = "maid-runner"
version = "2.0.0"
requires-python = ">=3.10"
dependencies = [
    "jsonschema>=4.25",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
typescript = ["tree-sitter>=0.23", "tree-sitter-typescript>=0.23"]
svelte = ["tree-sitter>=0.23", "tree-sitter-svelte>=1.0"]
all = ["maid-runner[typescript,svelte]"]
watch = ["watchdog>=6.0"]

[project.scripts]
maid = "maid_runner.cli.main:main"
```

### .maidrc.yaml (Project-Level Config)

Projects can optionally have a `.maidrc.yaml` at their root:

```yaml
# .maidrc.yaml - Project-level MAID configuration
manifest_dir: manifests/          # Where manifests live (default: manifests/)
schema_version: 2                 # Manifest schema version (default: 2)
default_validation_mode: implementation  # Default mode (default: implementation)
languages:                        # Enabled language validators
  - python
  - typescript
coherence:
  enabled: true                   # Run coherence checks with validate (default: false)
  checks:                         # Which checks to enable
    - duplicate
    - signature
    - boundary
    - naming
```

## Estimated Module Sizes

| Module | Estimated Lines | Notes |
|--------|----------------|-------|
| core/manifest.py | ~300 | YAML/JSON loading, schema validation |
| core/chain.py | ~350 | Chain resolution, merge, supersession |
| core/validate.py | ~400 | Validation orchestration engine |
| core/result.py | ~150 | Result types and serialization |
| core/snapshot.py | ~300 | Snapshot generation |
| core/types.py | ~200 | Shared dataclasses |
| core/config.py | ~80 | Config loading |
| validators/base.py | ~70 | ABC definition |
| validators/__init__.py | ~60 | Registry |
| validators/python.py | ~500 | Python AST validator (ported from current) |
| validators/typescript.py | ~1,200 | TypeScript tree-sitter validator (ported) |
| validators/svelte.py | ~250 | Svelte validator (ported) |
| graph/ (all) | ~1,500 | Mostly ported from current |
| coherence/ (all) | ~1,200 | Mostly ported from current |
| compat/v1_loader.py | ~200 | V1 JSON -> V2 conversion |
| cli/ (all) | ~500 | Thin wrappers |
| **Total** | **~7,300** | Down from 23,500 |

## External Dependencies

### Required (Core)

| Package | Version | Purpose |
|---------|---------|---------|
| jsonschema | >=4.25 | Manifest schema validation |
| pyyaml | >=6.0 | YAML manifest parsing |

### Optional (Plugins)

| Package | Extra | Purpose |
|---------|-------|---------|
| tree-sitter | `[typescript]` or `[svelte]` | AST parsing engine |
| tree-sitter-typescript | `[typescript]` | TypeScript/JavaScript grammar |
| tree-sitter-svelte | `[svelte]` | Svelte grammar |
| watchdog | `[watch]` | File system watch mode |
