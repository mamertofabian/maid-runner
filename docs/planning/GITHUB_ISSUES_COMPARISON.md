# MAID Runner: Current vs Roadmap (Quick Reference)

## Feature Comparison Matrix

### Core Validation (v1.2)

| Feature | Status | Notes |
|---------|--------|-------|
| JSON Schema Validation | ✅ DONE | Draft 7, full compliance checking |
| AST Implementation Validation | ✅ DONE | Python classes, functions, attributes |
| Behavioral Test Validation | ✅ DONE | Verify tests USE artifacts |
| Type Hint Validation | ✅ DONE | Complex types, generics, unions |
| Manifest Chain Merging | ✅ DONE | Chronological ordering, artifact inheritance |
| File Tracking Analysis | ✅ DONE | UNDECLARED/REGISTERED/TRACKED categorization |
| Semantic Validation | ✅ DONE | MAID principle enforcement |
| Snapshot Generation | ✅ DONE | From existing Python files |
| Version Management | ✅ DONE | Schema versioning support |

### CLI Commands (v1.2)

| Command | Status | Description |
|---------|--------|-------------|
| `maid validate` | ✅ DONE | Single or directory validation |
| `maid snapshot` | ✅ DONE | Generate snapshot from Python file |
| `maid test` | ✅ DONE | Run validation commands |
| `maid manifests` | ✅ DONE | List manifests for a file |
| `maid init` | ✅ DONE | Initialize MAID in project |
| `maid generate-stubs` | ✅ DONE | Create test stubs |
| `maid schema` | ✅ DONE | Output JSON schema |

### Performance (v1.2)

| Feature | Status | Notes |
|---------|--------|-------|
| Manifest Chain Caching | ❌ NOT DONE | Planned for v1.3 |
| Parallel Validation | ❌ NOT DONE | Planned for v1.3 |
| Incremental Validation | ❌ NOT DONE | Planned for v1.3 |
| Performance Benchmarks | ❌ NOT DONE | Planned for v1.3 |

### IDE/Editor Support (Future)

| Feature | Status | Timeline |
|---------|--------|----------|
| Language Server Protocol (LSP) | ❌ NOT DONE | v2.0 (Q2 2025) |
| VS Code Extension | ❌ NOT DONE | v2.0 (Q2 2025) |
| Real-time Validation | ❌ NOT DONE | v2.0 (Q2 2025) |
| Diagnostic Reporting | ❌ NOT DONE | v2.0 (Q2 2025) |

### Language Support (Future)

| Language | Status | Timeline |
|----------|--------|----------|
| Python | ✅ DONE | v1.2 |
| TypeScript | ❌ NOT DONE | v1.4+ |
| Go | ❌ NOT DONE | v1.4+ |
| Rust | ❌ NOT DONE | v1.4+ |

### Integration & Ecosystem (Future)

| Feature | Status | Timeline |
|---------|--------|----------|
| GitHub Actions Templates | ❌ NOT DONE | v1.3+ |
| Pre-commit Hooks | ❌ NOT DONE | v1.3+ |
| CI/CD Integration Guides | ❌ NOT DONE | v1.3+ |
| Python API | ❌ NOT DONE | v1.3+ |

### Documentation (Current)

| Document | Status | Location |
|----------|--------|----------|
| CLAUDE.md | ✅ DONE | Project root |
| ROADMAP.md | ✅ DONE | docs/ROADMAP.md |
| maid_specs.md | ✅ DONE | docs/maid_specs.md |
| README.md | ✅ DONE | Project root |
| API Documentation | ⏳ PARTIAL | Inline docstrings |
| Integration Guides | ❌ NOT DONE | Planned |

---

## What to Create Issues For

Based on the roadmap, here are the recommended GitHub issue categories:

### High Priority (v1.3 Q1 2025)
- [ ] Performance optimization - manifest chain caching
- [ ] Performance optimization - parallel validation
- [ ] Performance optimization - incremental validation
- [ ] Enhanced snapshot support improvements
- [ ] Performance benchmarks and profiling

### Medium Priority (v2.0 Q2 2025)
- [ ] Language Server Protocol (LSP) implementation
- [ ] VS Code extension development
- [ ] Real-time validation in editors
- [ ] Advanced diagnostic reporting

### Medium Priority (v1.3+ Q1-Q2 2025)
- [ ] GitHub Actions workflow templates
- [ ] Pre-commit hook integration
- [ ] CI/CD integration documentation
- [ ] Python API stabilization

### Lower Priority (v1.4+ Future)
- [ ] Multi-language support (TypeScript, Go, Rust)
- [ ] Advanced static analysis integration
- [ ] Machine learning for validation accuracy
- [ ] Formal verification of manifest chains
- [ ] Plugin system for custom validators

### Documentation (Ongoing)
- [ ] Complete API reference documentation
- [ ] Integration tutorials (Claude Code, Aider, Cursor)
- [ ] Migration guides
- [ ] Best practices guide
- [ ] Video demonstrations

---

## Current Gaps vs Roadmap

### Not Yet Implemented (From v1.3+ Roadmap)

1. **Performance Features**
   - No caching mechanism
   - No parallel validation
   - No incremental validation
   - No benchmarking suite

2. **IDE Integration**
   - No LSP server
   - No VS Code extension
   - No real-time validation
   - No editor integrations

3. **CI/CD Integration**
   - No GitHub Actions templates
   - No GitLab CI examples
   - No pre-commit hooks
   - No validation gates setup

4. **Python API**
   - CLI-only currently
   - No programmatic Python API
   - No library mode

5. **Multi-Language**
   - Python only
   - No TypeScript/JavaScript support
   - No Go support
   - No Rust support

6. **Reporting**
   - JSON report output not available
   - Markdown reports not available
   - CI-friendly formats not available

---

## What's Ready for Production Use

### CLI Usage
✅ Can be integrated via subprocess calls
✅ Clear exit codes (0 = success, 1 = failure)
✅ Structured error messages
✅ Quiet mode for scripting

### Validation Quality
✅ Comprehensive validation coverage
✅ 49 test cases covering all paths
✅ Deep AST analysis
✅ Cross-file behavioral validation

### Development Integration
✅ Works with Make/shell scripts
✅ Integration with MAID workflow
✅ Suitable for CI/CD pipelines
✅ Automation-friendly

---

## Quick Facts

| Aspect | Details |
|--------|---------|
| **Minimum Python Version** | 3.12+ |
| **Dependencies** | jsonschema>=4.25.1, pytest>=8.4.2 |
| **Project Type** | Validation framework (not a generator) |
| **Development Status** | Beta (v0.1.0) |
| **License** | MIT |
| **Repository** | GitHub: mamertofabian/maid-runner |

---

## How to Use This Summary

1. **Compare with Current State** - See what's implemented vs planned
2. **Create GitHub Issues** - Use the "What to Create Issues For" section
3. **Prioritize Work** - Follow the roadmap timeline (Q1 2025 = highest)
4. **Plan Integrations** - Focus on CLI for now, LSP later
5. **Set Expectations** - Know that performance optimization is coming in v1.3

---

## Next Steps for GitHub Issues

Recommended issue creation strategy:

### Phase 1: Create Meta-Issues (Group Related Work)
1. Epic: Performance Optimization (v1.3)
2. Epic: IDE Integration (v2.0)
3. Epic: Multi-Language Support (v1.4+)

### Phase 2: Create Detailed Issues per Epic
- Break down into specific, testable tasks
- Link to existing manifests where applicable
- Reference roadmap document

### Phase 3: Estimate and Schedule
- v1.3 issues → Q1 2025 milestone
- v2.0 issues → Q2 2025 milestone
- v1.4+ issues → Future backlog

---

## Documentation Resources

- **MAID Runner State Summary**: `MAID_RUNNER_STATE_SUMMARY.md` (comprehensive)
- **Official Roadmap**: `docs/ROADMAP.md`
- **MAID Specification**: `docs/maid_specs.md`
- **Project Guidelines**: `CLAUDE.md`
- **Key Learnings**: `docs/key_learnings_20250917.md`
- **Video Series Roadmap**: `docs/VIDEO_SERIES_ROADMAP.md`

