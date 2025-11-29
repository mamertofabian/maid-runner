# MAID Runner Roadmap

**Project:** MAID Runner - Tool-Agnostic Validation Framework
**Status:** Active Development
**Current Version:** 1.3
**Last Updated:** 2025-11-30

## Vision

MAID Runner is a **validation-only framework** that ensures code artifacts align with declarative manifests. It does NOT create files, generate code, or automate development. Instead, it provides robust validation that external tools (AI agents, IDEs, CI/CD) can integrate with.

## Core Principles

1. **Validation Only** - No file creation, no code generation
2. **Tool-Agnostic** - Works with any development tool via CLI
3. **Exit Code Driven** - Clear 0/1 signals for automation
4. **No Interactive Prompts** (in core tools) - Automation-friendly
5. **Focused Responsibility** - Do one thing exceptionally well

## Current State (v1.3)

### ✅ Completed Features

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
- `maid init` - Initialize MAID workflow
- `maid schema` - Output manifest JSON schema

**Validation Modes:**
- Strict mode (creatableFiles - exact match)
- Permissive mode (editableFiles - contains at least)
- Implementation mode (code DEFINES artifacts)
- Behavioral mode (tests USE artifacts)

**Test Coverage:**
- 1100+ comprehensive tests
- All core validation paths covered
- Integration tests for all features
- Multi-language validation tests

## Roadmap

### Phase 1: Core Enhancements (Q1 2025)

**Goal:** Improve validation accuracy and developer feedback

#### Milestone 1.1: Manifest Schema v2.0
**Status:** Planned
**Duration:** 2-3 weeks

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
**Status:** In Progress
**Duration:** 2 weeks

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
**Status:** Planned
**Duration:** 2 weeks

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

#### Milestone 2.1: Language Server Protocol (LSP)
**Status:** Planned
**Duration:** 4-5 weeks

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
**Status:** Planned
**Duration:** 3-4 weeks
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
**Status:** Planned
**Duration:** 2 weeks

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

#### Milestone 3.1: CI/CD Templates
**Status:** Planned
**Duration:** 2 weeks

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
**Status:** Planned
**Duration:** 2 weeks

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
**Status:** Planned
**Duration:** 1 week

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

#### Milestone 4.1: Documentation
**Status:** Ongoing

**Features:**
- Complete API reference
- Integration tutorials
- Migration guides
- Video demonstrations
- Best practices guide

#### Milestone 4.2: Performance & Stability
**Status:** Ongoing

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
- **Validation Accuracy:** >99% precision on artifact detection
- **Performance:** <100ms for typical manifest validation
- **Reliability:** 0 critical bugs in production
- **Coverage:** >90% test coverage maintained

### Adoption Metrics
- **External Tool Integrations:** 3+ tools using MAID Runner
- **VS Code Extension:** 100+ active installs (6 months)
- **Documentation:** <5% bounce rate on getting started
- **Community:** 10+ external contributors

### Quality Metrics
- **API Stability:** Semantic versioning, no breaking changes in minor versions
- **Documentation:** 100% public API documented
- **Error Messages:** >80% of users can self-resolve errors

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

## Post-v1.3 Vision

### Future Enhancements (v1.4+)
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

MAID Runner v1.3 will be a **production-ready validation framework** that external tools can confidently integrate with. By staying focused on validation, we ensure:

1. **Universal Compatibility** - Any tool can use MAID Runner
2. **Single Responsibility** - One thing done exceptionally well
3. **Long-term Stability** - Focused scope means fewer breaking changes
4. **Tool Innovation** - External tools compete on automation quality

**MAID Runner validates. External tools innovate.**

---

**Note:** For automation features (Guardian Agent, automated manifest generation, etc.), see `docs/future/maid-agent/` - these will be built as separate tools that **use** MAID Runner for validation.
