# MAID Runner v2 - Rewrite Overview

## Document Purpose

This document is the entry point for the MAID Runner v2 rewrite specification. It defines the vision, principles, success criteria, and scope of the rewrite. All other spec documents reference this as context.

## What Is MAID Runner

MAID Runner is a **validation framework** for Manifest-driven AI Development (MAID). It validates that code artifacts match their declarative manifest specifications, enforcing architectural contracts through AST-based validation.

**Core value proposition:** Dual-constraint validation for AI code generation:
1. **Behavioral** (tests pass) - code works correctly
2. **Structural** (code matches blueprint) - code matches the architectural specification

## Why Rewrite

The current codebase (v0.11.x) grew organically through 160+ sequential tasks. This created:

| Problem | Metric | Impact |
|---------|--------|--------|
| Manifest proliferation | 165 manifests for 23K LOC | 1 manifest per ~142 lines of code |
| Monolithic CLI | validate.py = 2,087 lines | Logic trapped in presentation layer |
| Subprocess integration | 3 ecosystem tools call CLI via subprocess | No type-safe library API |
| Heavy required deps | tree-sitter always required | Python-only users pay for TS/Svelte |
| Sequential numbering | task-001 through task-160, alphabetic suffixes | Blocks parallel work |
| Single-file manifests | expectedArtifacts targets ONE file | Multi-file features need N manifests |
| Legacy schema fields | parameters vs args, validationCommand vs validationCommands | Confusing duplication |
| Task-numbered tests | test_task_086_create_svelte_validator.py | Impossible to navigate by domain |
| Test volume | 88K lines of tests (3.7:1 ratio) | Maintenance burden |

## Design Principles

### P1: Library-First, CLI-Second
The primary interface is a Python library with clean API. The CLI is a thin wrapper (~500 lines total). Ecosystem tools (maid-lsp, maid-runner-mcp, maid-agents) import the library directly instead of spawning subprocesses.

### P2: Multi-File Manifests
One manifest per *feature*, not per *file*. A manifest can declare artifacts across multiple files. This is the single biggest reduction in manifest count.

### P3: Plugin Architecture for Languages
Core ships with Python validation only (stdlib `ast`, zero extra deps). TypeScript and Svelte are optional extras installed via `pip install maid-runner[typescript]`.

### P4: Clean Schema, No Legacy
Manifest schema v2 has ONE way to express everything. No backward-compatible dual formats. V1 JSON manifests are supported via a separate compatibility loader.

### P5: Domain-Organized Tests
Tests mirror source structure (`tests/core/`, `tests/validators/`, etc.), not task numbers. Each test file corresponds to a source module.

### P6: Separation of Concerns
Four distinct layers with clear boundaries:
- **Core** - manifest loading, chain resolution, validation orchestration
- **Validators** - language-specific AST analysis (pluggable)
- **Features** - graph, coherence (optional modules)
- **CLI** - argument parsing and output formatting only

### P7: YAML-Native Manifests
YAML is the primary manifest format (comments, less noise, readable). JSON manifests from v1 are still loadable via compatibility layer.

## What Changes vs What Stays

### Stays the Same
- All current validation capabilities (behavioral + implementation modes)
- Manifest chain resolution and supersession logic
- Three-level file tracking (UNDECLARED, REGISTERED, TRACKED)
- Strict vs permissive validation (creatableFiles vs editableFiles)
- Knowledge graph system (nodes, edges, queries, export)
- Coherence checks (7 architectural validators)
- Watch mode (single-manifest and multi-manifest)
- Snapshot generation (Python, TypeScript, Svelte)
- CLI command set (validate, test, snapshot, init, graph, etc.)
- All current edge cases and behaviors

### Changes
- Manifest format: JSON single-file -> YAML multi-file (with v1 compat)
- Manifest naming: task-NNN -> semantic slugs with timestamps
- Architecture: CLI-first -> library-first with thin CLI
- Validators: built-in -> plugin architecture with optional deps
- Tests: task-numbered -> domain-organized
- CLI modules: monolithic -> thin wrappers calling library
- Package structure: flat -> layered (core/, validators/, graph/, coherence/)
- Integration: subprocess -> direct library import API

## Success Criteria

1. **All current validation behaviors preserved** - same inputs produce same outputs
2. **Library API usable without CLI** - `from maid_runner import validate` works
3. **`pip install maid-runner` has zero tree-sitter deps** - Python-only users unaffected
4. **CLI total < 500 lines** - all logic lives in library layer
5. **Multi-file manifests work** - single manifest can validate artifacts across N files
6. **V1 JSON manifests still loadable** - backward compatibility for existing projects
7. **All ecosystem tools can import library** - no subprocess wrapping needed
8. **Test count reduction ~60%** - same coverage, domain-organized, no redundancy

## Spec Document Index

| Document | Scope |
|----------|-------|
| [01-architecture.md](01-architecture.md) | Package structure, module dependencies, data flow |
| [02-manifest-schema-v2.md](02-manifest-schema-v2.md) | Complete YAML manifest format specification |
| [03-data-types.md](03-data-types.md) | All internal types, dataclasses, enums |
| [04-core-manifest.md](04-core-manifest.md) | Manifest loading, parsing, chain resolution |
| [05-core-validation.md](05-core-validation.md) | Validation engine (behavioral + implementation) |
| [06-validators.md](06-validators.md) | Plugin architecture + language validators |
| [07-graph-module.md](07-graph-module.md) | Knowledge graph system |
| [08-coherence-module.md](08-coherence-module.md) | Coherence validation checks |
| [09-cli.md](09-cli.md) | CLI commands specification |
| [10-public-api.md](10-public-api.md) | Library API surface and usage |
| [11-testing-strategy.md](11-testing-strategy.md) | Test organization and approach |
| [12-migration-plan.md](12-migration-plan.md) | Phased migration from v1 |
| [13-backward-compatibility.md](13-backward-compatibility.md) | V1 manifest support |
| [14-progress-tracker.md](14-progress-tracker.md) | Machine-readable progress checklist, session handoff protocol |
| [15-golden-tests.md](15-golden-tests.md) | Concrete input/output test cases for every module |
| [16-porting-reference.md](16-porting-reference.md) | Critical algorithms from current codebase to preserve |

## Conventions Used in These Specs

- **File paths** are relative to project root (`maid_runner/core/manifest.py`)
- **Class/function signatures** use Python type annotation syntax
- **MUST/SHOULD/MAY** follow RFC 2119 semantics
- **Cross-references** use `[spec-name](filename.md)` links
- **Code blocks** show exact intended implementation signatures
- **Tables** define field-level specifications for data structures
