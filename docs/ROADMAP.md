# MAID Runner Roadmap

**Project:** MAID Runner - Tool-Agnostic Validation Framework
**Status:** Active Development
**Current Version:** 0.1.3 (Feature Set v1.3)
**Last Updated:** 2025-11-30

## Vision

MAID Runner is a **validation-only framework** that ensures code artifacts align with declarative manifests. It does NOT create files, generate code, or automate development. Instead, it provides robust validation that external tools (AI agents, IDEs, CI/CD) can integrate with.

## Core Principles

1. **Validation Only** - No file creation, no code generation
2. **Tool-Agnostic** - Works with any development tool via CLI
3. **Exit Code Driven** - Clear 0/1 signals for automation
4. **No Interactive Prompts** (in core tools) - Automation-friendly
5. **Focused Responsibility** - Do one thing exceptionally well

## Current State (v0.1.3 - Feature Set v1.3)

### Implemented Features

**Core Validation:**
- Schema validation (manifest JSON structure)
- AST-based implementation validation
- Behavioral test validation (tests USE artifacts)
- Type hint validation
- Manifest chain merging
- Supersedes relationship handling
- Snapshot generation from existing code

**Multi-Language Support:**
- **Python** - Full support via Python AST
- **TypeScript/JavaScript** - Production-ready support via tree-sitter
  - Extensions: `.ts`, `.tsx`, `.js`, `.jsx`
  - Complete language coverage (classes, interfaces, types, enums, namespaces, functions, methods)
  - Framework support (Angular, React, NestJS, Vue)
  - 99.9% TypeScript construct coverage
- Language-agnostic validator architecture via `BaseValidator` abstract class

**CLI Tools:**
- `maid validate` - Core validation CLI (Python & TypeScript)
- `maid snapshot` - Snapshot generation (Python & TypeScript)
- `maid snapshot-system` - System-wide manifest aggregation (cross-language)
- `maid test` - Run validation commands from manifests
- `maid manifests` - List manifests referencing a file
- `maid generate-stubs` - Generate test stubs (Python & TypeScript)
- `maid init` - Initialize MAID workflow (supports multiple AI dev tools: Claude Code, Cursor, Windsurf, generic)
- `maid howto` - Interactive guide to MAID methodology
- `maid schema` - Output manifest JSON schema

**Validation Modes:**
- Strict mode (creatableFiles - exact match)
- Permissive mode (editableFiles - contains at least)
- Implementation mode (code DEFINES artifacts)
- Behavioral mode (tests USE artifacts)

**Test Coverage:**
- 1,142 comprehensive tests (100% pass rate)
- All core validation paths covered
- Integration tests for all features
- Multi-language validation tests
- 67 test files covering edge cases and framework patterns

**Additional Implemented Features:**
- File tracking analysis with 3-level compliance system (Undeclared/Registered/Tracked)
- Language auto-detection for project initialization
- Semantic validation to detect multi-file modification attempts
- Async function detection for Python and TypeScript
- Comprehensive type hint validation with union types and generics
- Published on PyPI as `maid-runner` package

## Roadmap

### Phase 1: Core Enhancements (Q1 2025)

**Goal:** Improve validation accuracy and developer feedback

**Status:** Not Started

#### Milestone 1.1: Manifest Schema v2.0
**Status:** Not Started
**Estimated Duration:** 2-3 weeks

**Features:**
- Enhanced schema with richer metadata
- Support for class inheritance (`bases` field)
- Multiple validation command support
- Explicit version field
- Migration tooling from v1.2 to v2.0

**Deliverables:**
- `validators/schemas/manifest.schema.v2.json`
- Migration script: `migrate_manifests.py`
- Backward compatibility with v1.2
- Documentation updates

#### Milestone 1.2: Enhanced Snapshot Support
**Status:** Not Started
**Estimated Duration:** 2 weeks
**Note:** Basic snapshot generation for Python and TypeScript is functional

**Features:**
- Improved snapshot generation algorithm
- Better handling of snapshot supersedes chains
- Validation optimization for snapshot-heavy histories
- Snapshot verification tools

**Deliverables:**
- Enhanced `generate_snapshot.py`
- Snapshot validation tests
- Performance improvements for large chains

#### Milestone 1.3: Validation Performance
**Status:** Not Started
**Estimated Duration:** 2 weeks
**Note:** Validation completes in milliseconds for typical manifests, but no formal benchmarks exist

**Features:**
- Caching for manifest chain resolution
- Incremental validation support
- Parallel validation for multiple manifests
- Performance benchmarks

**Deliverables:**
- 50%+ performance improvement for large chains
- <100ms validation for typical manifests
- Benchmark suite

### Phase 2: Developer Experience (Q2 2025)

**Goal:** Make validation feedback immediate and actionable

**Status:** Not Started

#### Milestone 2.1: Language Server Protocol (LSP)
**Status:** Not Started
**Estimated Duration:** 4-5 weeks

**Features:**
- Real-time manifest validation in editors
- Diagnostic reporting with precise locations
- Hover information for artifacts
- Quick fixes for common errors
- Document synchronization

**Deliverables:**
- `maid_lsp/` - LSP server implementation
- Integration with pygls library
- Documentation for IDE integration

**Why LSP?**
- Tool-agnostic (works with any LSP-compatible editor)
- Real-time feedback without manual validation
- Maintains validation-only principle (no code generation)

#### Milestone 2.2: VS Code Extension
**Status:** Not Started
**Estimated Duration:** 3-4 weeks
**Dependencies:** Milestone 2.1

**Features:**
- Manifest explorer view
- Inline validation indicators
- Test execution integration (run validationCommand)
- Status bar with validation status
- Quick navigation to errors

**Deliverables:**
- VS Code extension (marketplace)
- Extension documentation
- Screenshots and tutorials

**Scope:**
- Visualization and feedback ONLY
- No code generation or automation
- Leverages LSP server for validation

#### Milestone 2.3: Validation Reporting
**Status:** Not Started
**Estimated Duration:** 2 weeks

**Features:**
- JSON report output
- Markdown report generation
- CI-friendly output format
- Historical validation tracking
- Validation badges for READMEs

**Deliverables:**
- Enhanced `--output-format` flag
- Report templates
- CI integration examples

### Phase 3: Integration & Ecosystem (Q3 2025)

**Goal:** Make MAID Runner easy to integrate with external tools

**Status:** Not Started

#### Milestone 3.1: CI/CD Templates
**Status:** Not Started
**Estimated Duration:** 2 weeks
**Note:** PyPI publishing workflow exists in `.github/workflows/publish.yml`

**Features:**
- GitHub Actions workflow templates
- GitLab CI configuration examples
- Pre-commit hook templates
- Validation gates for pull requests
- Automated reporting in CI

**Deliverables:**
- `.github/workflows/maid-validation.yml`
- Pre-commit hook scripts
- Integration documentation

#### Milestone 3.2: External Tool Integration Guides
**Status:** Not Started
**Estimated Duration:** 2 weeks
**Note:** Planning documents exist in `docs/future/claude-code-integration/`

**Features:**
- Integration guide for Claude Code
- Integration guide for Aider
- Integration guide for Cursor
- Generic integration template
- Best practices documentation

**Deliverables:**
- Integration documentation
- Code examples for each tool
- Troubleshooting guides

#### Milestone 3.3: Python API
**Status:** Partially Complete
**Estimated Duration:** 1 week
**Note:** Basic Python API exists and is exported via `__init__.py`

**Features:**
- Clean Python API for validation
- Programmatic access to all features
- Type hints and documentation
- API stability guarantees

**Deliverables:**
- `maid_runner` Python package
- API documentation
- Usage examples

### Phase 4: Polish & Production Readiness (Q4 2025)

**Status:** Partially Complete

#### Milestone 4.1: Documentation
**Status:** Partially Complete

**Features:**
- Complete API reference
- Integration tutorials
- Migration guides
- Video demonstrations
- Best practices guide

#### Milestone 4.2: Performance & Stability
**Status:** Partially Complete
**Note:** 1,142 tests with 100% pass rate, comprehensive edge case handling

**Features:**
- Performance profiling and optimization
- Edge case handling
- Error message improvements
- Stability testing

## Features We Will NOT Implement

The following features belong in **external tools** (like MAID Agent, Claude Code, etc.):

❌ **Automated Manifest Generation** - External tools create manifests
❌ **Guardian Agent Framework** - External tools implement agents
❌ **Scaffold and Fill** - External tools generate code
❌ **Fix Dispatch System** - External tools orchestrate fixes
❌ **Workflow Automation** - External tools manage development flow
❌ **AI Integration** - External tools integrate with LLMs

**Rationale:** MAID Runner validates. External tools automate.

## Success Metrics

### Technical Metrics
- **Validation Accuracy:** >99% precision on artifact detection ✅ Achieved
- **Performance:** Sub-second validation for typical manifests ✅ Achieved
- **Reliability:** 0 critical bugs in production ✅ Achieved
- **Coverage:** 1,142 tests with 100% pass rate ✅ Achieved

### Adoption Metrics (Goals)
- **External Tool Integrations:** 3+ tools using MAID Runner
- **PyPI Downloads:** Steady growth in package adoption
- **Documentation:** Clear getting started guides
- **Community:** External contributors

### Quality Metrics
- **API Stability:** Semantic versioning maintained ✅ Achieved
- **Documentation:** Public API documented with docstrings ✅ Achieved
- **Error Messages:** User-friendly validation output ✅ Achieved
- **Multi-Language Support:** Python and TypeScript production-ready ✅ Achieved

## External Tool Integration

MAID Runner is designed to be **used** by other tools:

```
┌─────────────────────────────────┐
│   External Tools                │
│   - MAID Agent (future)         │
│   - Claude Code                 │
│   - Aider                       │
│   - Cursor                      │
│   - Custom scripts              │
└─────────────────────────────────┘
              │
              │ subprocess.run()
              ▼
┌─────────────────────────────────┐
│   MAID Runner                   │
│   validate_manifest.py          │
│   generate_snapshot.py          │
└─────────────────────────────────┘
```

**Integration is simple:**
```python
import subprocess

result = subprocess.run([
    "python", "validate_manifest.py",
    "manifests/task-013.manifest.json",
    "--use-manifest-chain",
    "--quiet"
], capture_output=True)

if result.returncode == 0:
    print("✓ Valid")
else:
    print(f"✗ Errors: {result.stderr}")
```

## Future Development

### Potential Enhancements
- Additional language support (Go, Rust, Java, C#)
- Advanced static analysis integration
- Formal verification of manifest chains
- Plugin system for custom validators

### Research Areas
- Machine learning for validation accuracy
- Predictive validation (detect issues before implementation)
- Cross-repository validation
- Performance optimizations for massive codebases

## Conclusion

MAID Runner is a **production-ready validation framework** that external tools can confidently integrate with. By staying focused on validation, the framework ensures:

1. **Universal Compatibility** - Any tool can use MAID Runner
2. **Single Responsibility** - One thing done exceptionally well
3. **Long-term Stability** - Focused scope means fewer breaking changes
4. **Tool Innovation** - External tools compete on automation quality

**MAID Runner validates. External tools innovate.**

---

**Note:** For automation features (Guardian Agent, automated manifest generation, etc.), see `docs/future/maid-agent/` - these are designed as separate tools that **use** MAID Runner for validation.
