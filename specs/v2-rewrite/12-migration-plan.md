# MAID Runner v2 - Migration Plan

**References:** [00-overview.md](00-overview.md), [01-architecture.md](01-architecture.md), [13-backward-compatibility.md](13-backward-compatibility.md)

## Strategy: Strangler Fig

We do NOT rewrite from scratch in one shot. Instead, we build the new architecture alongside the old, gradually migrating functionality until the old code can be removed. This ensures:

- The project is always in a working state
- Each phase can be tested independently
- Rollback is possible at any phase boundary
- Existing ecosystem tools keep working throughout

## Phase Overview

| Phase | Focus | Deliverable | Risk |
|-------|-------|-------------|------|
| **1** | Foundation | Core types + manifest loading + v2 schema | Low |
| **2** | Validation Engine | Library API for validate + chain | Medium |
| **3** | Validators | Plugin architecture + port all validators | Medium |
| **4** | CLI Rewrite | Thin CLI wrapping library API | Low |
| **5** | Features | Graph + coherence using new architecture | Low |
| **6** | Ecosystem | Update maid-lsp, maid-runner-mcp, maid-agents | Medium |
| **7** | Cleanup | Remove old code, finalize tests | Low |

## Phase 1: Foundation

**Goal:** Establish the new package structure and core data types.

### Tasks

1. **Create new package structure**
   ```
   maid_runner/core/__init__.py
   maid_runner/core/types.py
   maid_runner/core/result.py
   maid_runner/core/config.py
   maid_runner/compat/__init__.py
   maid_runner/schemas/manifest.v2.schema.json
   ```

2. **Implement core data types** (from [03-data-types.md](03-data-types.md))
   - All enums: ArtifactKind, TaskType, ValidationMode, FileMode, ErrorCode, Severity
   - All dataclasses: ArgSpec, ArtifactSpec, FileSpec, DeleteSpec, Manifest
   - All result types: ValidationError, ValidationResult, etc.

3. **Implement manifest loading** (from [04-core-manifest.md](04-core-manifest.md))
   - `maid_runner/core/manifest.py`
   - YAML v2 loading and parsing
   - Schema validation against `manifest.v2.schema.json`
   - `load_manifest()`, `save_manifest()`, `validate_manifest_schema()`

4. **Implement V1 compatibility loader** (from [13-backward-compatibility.md](13-backward-compatibility.md))
   - `maid_runner/compat/v1_loader.py`
   - Convert v1 JSON format to v2 Manifest dataclass
   - Auto-detection in `load_manifest()` based on file extension and content

5. **Write foundation tests**
   - `tests/core/test_manifest.py`
   - `tests/core/test_result.py`
   - `tests/compat/test_v1_loader.py`
   - `tests/fixtures/manifests/v2/*.manifest.yaml` (sample manifests)
   - `tests/fixtures/manifests/v1/*.manifest.json` (from existing manifests)

### Acceptance Criteria

- [ ] All v2 YAML manifests load correctly into Manifest dataclass
- [ ] All current v1 JSON manifests load correctly via compat layer
- [ ] Schema validation catches invalid manifests
- [ ] Multi-file manifests (files.create with multiple entries) parse correctly
- [ ] `save_manifest()` produces valid YAML that round-trips
- [ ] All data types are frozen (immutable)
- [ ] All result types serialize to JSON correctly

### What Stays Working

The existing CLI and validators are UNTOUCHED. Current `maid validate` still works.

---

## Phase 2: Validation Engine

**Goal:** Implement the core validation logic as a library, independent of CLI.

### Tasks

1. **Implement ManifestChain** (from [04-core-manifest.md](04-core-manifest.md))
   - `maid_runner/core/chain.py`
   - Discovery, supersession resolution, artifact merge
   - Porting logic from current `manifest_validator.py` `discover_related_manifests()` and `ManifestRegistry`

2. **Implement ValidationEngine** (from [05-core-validation.md](05-core-validation.md))
   - `maid_runner/core/validate.py`
   - `validate()`, `validate_all()` convenience functions
   - Behavioral validation (porting from `_behavioral_validation.py`)
   - Implementation validation (porting from `validate.py` + `_artifact_validation.py`)
   - File tracking analysis (porting from `file_tracker.py`)

3. **Implement type comparison** (porting from `_type_normalization.py`, `_type_validation.py`)
   - `maid_runner/core/_type_compare.py`
   - Type normalization (Optional/Union, PEP 585, etc.)

4. **Implement test runner** (porting from `test.py` + `_batch_test_runner.py`)
   - `maid_runner/core/test_runner.py`
   - `run_tests()`, `run_manifest_tests()`
   - Batch mode optimization

5. **Write validation tests**
   - `tests/core/test_chain.py`
   - `tests/core/test_validate.py`
   - `tests/core/test_type_compare.py`

### Acceptance Criteria

- [ ] `validate("manifests/xxx.manifest.yaml")` works for v2 YAML manifests
- [ ] `validate("manifests/xxx.manifest.json")` works for v1 JSON manifests
- [ ] `validate_all("manifests/")` validates all active manifests
- [ ] ManifestChain correctly resolves supersession
- [ ] ManifestChain correctly merges artifacts for multi-manifest files
- [ ] Behavioral validation detects artifact usage in tests
- [ ] Implementation validation detects artifact definitions in code
- [ ] Strict mode (create) rejects unexpected public artifacts
- [ ] Permissive mode (edit) allows extra public artifacts
- [ ] Type comparison handles all normalization cases from current suite
- [ ] File tracking classifies files as UNDECLARED/REGISTERED/TRACKED

### Porting Notes

The current validation logic is spread across:
- `cli/validate.py` (2,087 lines) - most logic is here
- `validators/manifest_validator.py` - artifact collection delegation
- `cli/_behavioral_validation.py` - behavioral mode
- `cli/_text_mode_validation.py` - text output
- `cli/_validation_orchestration.py` - orchestration
- `validators/_artifact_validation.py` - single artifact comparison
- `validators/_type_validation.py` - type hint comparison
- `validators/_type_normalization.py` - type normalization
- `validators/file_tracker.py` - file tracking

These are consolidated into:
- `core/validate.py` (~400 lines) - orchestration
- `core/chain.py` (~350 lines) - chain resolution
- `core/_type_compare.py` (~250 lines) - type comparison
- `core/_file_discovery.py` (~100 lines) - source file discovery

---

## Phase 3: Validators

**Goal:** Implement the plugin architecture and port all language validators.

### Tasks

1. **Implement validator infrastructure**
   - `maid_runner/validators/__init__.py` - ValidatorRegistry
   - `maid_runner/validators/base.py` - BaseValidator ABC, FoundArtifact, CollectionResult

2. **Port PythonValidator**
   - `maid_runner/validators/python.py`
   - Port from current `manifest_validator.py` `_ArtifactCollector` and behavioral collection
   - Port test stub generation from `cli/snapshot.py`

3. **Port TypeScriptValidator**
   - `maid_runner/validators/typescript.py`
   - Port from current `validators/typescript_validator.py` (1,677 lines)
   - Port test stub generation from `cli/snapshot.py` TypeScript section
   - Port test runner from `validators/typescript_test_runner.py`

4. **Port SvelteValidator**
   - `maid_runner/validators/svelte.py`
   - Port from current `validators/svelte_validator.py`

5. **Update pyproject.toml** for optional dependencies
   ```toml
   [project.optional-dependencies]
   typescript = ["tree-sitter>=0.23", "tree-sitter-typescript>=0.23"]
   svelte = ["tree-sitter>=0.23", "tree-sitter-svelte>=1.0"]
   ```

6. **Write validator tests**
   - `tests/validators/test_registry.py`
   - `tests/validators/test_python.py`
   - `tests/validators/test_typescript.py`
   - `tests/validators/test_svelte.py`

### Acceptance Criteria

- [ ] PythonValidator detects all artifact types (class, function, method, attribute, async, enum, etc.)
- [ ] PythonValidator filters self/cls correctly
- [ ] PythonValidator handles generics, ABC, decorators
- [ ] TypeScriptValidator detects classes, interfaces, types, enums, namespaces
- [ ] TypeScriptValidator handles arrow functions, JSX/TSX, generators
- [ ] TypeScriptValidator private member filtering (_prefix, #prefix, private keyword)
- [ ] SvelteValidator extracts and delegates to TypeScriptValidator
- [ ] ValidatorRegistry auto-registers available validators
- [ ] Missing tree-sitter produces helpful error message
- [ ] `pip install maid-runner` (without extras) has no tree-sitter dependency
- [ ] `pip install maid-runner[typescript]` enables TypeScript validation

---

## Phase 4: CLI Rewrite

**Goal:** Replace the monolithic CLI with thin wrappers around the library API.

### Tasks

1. **Create new CLI structure**
   ```
   maid_runner/cli/main.py           # New: argparse + routing
   maid_runner/cli/commands/          # New: one file per command
   maid_runner/cli/format.py          # New: output formatters
   ```

2. **Implement each command as thin wrapper** (from [09-cli.md](09-cli.md))
   - Each command: parse args -> call library -> format output -> return exit code
   - Port watch mode from current `cli/test.py` and `cli/validate.py`

3. **Update entry point in pyproject.toml**
   - Keep `maid = "maid_runner.cli.main:main"` but point to new main.py

4. **Write CLI tests**
   - `tests/cli/test_validate_cmd.py`
   - `tests/cli/test_test_cmd.py`
   - `tests/cli/test_snapshot_cmd.py`
   - `tests/cli/test_format.py`

### Acceptance Criteria

- [ ] All current CLI commands produce equivalent output
- [ ] `maid validate` works identically to current behavior
- [ ] `maid test` works identically (including batch mode)
- [ ] `maid snapshot` produces valid manifests
- [ ] `maid init` generates correct files for each tool
- [ ] Watch mode works for single and multi-manifest
- [ ] `--json` flag works on all commands
- [ ] Exit codes match specification (0, 1, 2)
- [ ] Total CLI code < 500 lines

### Migration Approach

During this phase, both old and new CLI code exist. The entry point switches to the new main.py, which imports from the library. The old `cli/validate.py`, `cli/test.py`, etc. are not deleted yet (that's Phase 7).

---

## Phase 5: Features

**Goal:** Port graph and coherence modules to new architecture.

### Tasks

1. **Port graph module**
   - `maid_runner/graph/model.py` - Mostly copy from current (clean code)
   - `maid_runner/graph/builder.py` - Update to use new Manifest/ManifestChain types
   - `maid_runner/graph/query.py` - Port query logic
   - `maid_runner/graph/export.py` - Port exporters

2. **Port coherence module**
   - `maid_runner/coherence/engine.py` - Update to use new types
   - `maid_runner/coherence/result.py` - Port result types
   - `maid_runner/coherence/checks/*.py` - Port all 7 checks

3. **Write feature tests**
   - `tests/graph/test_*.py`
   - `tests/coherence/test_*.py`

### Acceptance Criteria

- [ ] Knowledge graph builds from new ManifestChain
- [ ] All query types work (definition, dependents, cycles, impact)
- [ ] All export formats produce valid output (JSON, DOT, GraphML)
- [ ] All 7 coherence checks produce equivalent results
- [ ] CoherenceEngine integrates with ValidationEngine

---

## Phase 6: Ecosystem Update

**Goal:** Update ecosystem tools to use library imports instead of subprocess.

### Tasks

1. **Update maid-lsp**
   - Replace subprocess calls with `from maid_runner import validate`
   - Update diagnostic generation to use `ValidationResult` directly

2. **Update maid-runner-mcp**
   - Replace subprocess calls with library imports
   - Update MCP tool handlers to use library API

3. **Update maid-agents**
   - Replace subprocess calls where possible
   - Note: some subprocess usage may be intentional for isolation

4. **Update documentation**
   - README with new YAML examples
   - Migration guide for existing users
   - API reference

### Acceptance Criteria

- [ ] maid-lsp works with library imports (no subprocess for validation)
- [ ] maid-runner-mcp works with library imports
- [ ] maid-agents updated to use library where appropriate
- [ ] All ecosystem tools pass their own test suites

---

## Phase 7: Cleanup

**Goal:** Remove old code, finalize tests, prepare release.

### Tasks

1. **Remove old CLI modules**
   - Delete `cli/validate.py` (old 2,087-line monolith)
   - Delete `cli/test.py` (old)
   - Delete `cli/snapshot.py` (old)
   - Delete `cli/init.py` (old)
   - Delete all `cli/_*.py` helper modules

2. **Remove old validator integration code**
   - Delete `validators/manifest_validator.py` (replaced by core/validate.py + validators/python.py)
   - Delete `validators/semantic_validator.py` (merged into core/validate.py)
   - Delete `validators/_artifact_validation.py`, `_type_validation.py`, etc.

3. **Remove old cache module** (replaced by ManifestChain's built-in caching)
   - Delete `cache/` directory

4. **Remove old test files**
   - Delete all `tests/test_task_*.py` files
   - Delete all `tests/_test_task_*.py` files
   - Verify new tests have equivalent coverage

5. **Final validation**
   - Run full test suite
   - Run coverage report
   - Run linting and type checking
   - Verify `maid validate` on the project itself
   - Test `pip install` from clean venv

6. **Version bump to 2.0.0**
   - Update `__version__.py`
   - Update `pyproject.toml`
   - Update `README.md`
   - Create release notes

### Acceptance Criteria

- [ ] No old code remains
- [ ] All tests pass
- [ ] Coverage meets targets (see [11-testing-strategy.md](11-testing-strategy.md))
- [ ] `pip install maid-runner` works (Python-only, no tree-sitter)
- [ ] `pip install maid-runner[all]` works (all languages)
- [ ] `maid validate` passes on the project's own manifests
- [ ] Type checking passes (`mypy`)
- [ ] Linting passes (`ruff`, `black`)

---

## Timeline Estimate

| Phase | Dependencies | Estimated Effort |
|-------|-------------|-----------------|
| Phase 1: Foundation | None | Small |
| Phase 2: Validation Engine | Phase 1 | Large |
| Phase 3: Validators | Phase 1 | Large |
| Phase 4: CLI Rewrite | Phase 2, 3 | Medium |
| Phase 5: Features | Phase 2, 3 | Medium |
| Phase 6: Ecosystem | Phase 4, 5 | Medium |
| Phase 7: Cleanup | Phase 6 | Small |

**Phases 2 and 3 can be done in parallel** since validators don't depend on the validation engine (they have separate interfaces).

## Rollback Strategy

At any phase boundary:
- If the new code is broken, the old code is still present and functional
- The entry point can be switched back to old `cli/main.py`
- Old tests still run against old code
- Git branch structure supports easy rollback

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Behavior regression | Port tests from old suite, run both old and new tests during transition |
| TypeScript edge cases | Keep current test_task_053/076/077/078/153-159 test cases as reference |
| Performance regression | Benchmark chain resolution and batch validation at each phase |
| Ecosystem breakage | Phase 6 explicitly updates all consumers; old subprocess API keeps working |
| V1 manifest loss | Compat layer runs on all existing project manifests as integration test |
