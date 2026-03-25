# MAID Runner v2 - Progress Tracker & Session Handoff Protocol

**References:** [12-migration-plan.md](12-migration-plan.md)

## Purpose

This document is the **machine-readable progress tracker** for the v2 rewrite. An autonomous agent starting a new session MUST read this file first to determine what's done, what's in progress, and what to do next.

## How to Use This Document

### Starting a New Session

1. Read this file
2. Find the current phase (first phase with unchecked items)
3. Find the current task within that phase (first unchecked item)
4. Read the corresponding spec document for that task
5. Read the "Session State" section below for any in-progress notes
6. Continue implementation

### During Implementation

- After completing each task, update the checkbox: `[ ]` -> `[x]`
- After completing each phase, update the phase status
- If stopping mid-task, update the "Session State" section with what's done and what remains
- Run the verification commands before marking a phase complete

### MAID Workflow During Rewrite

**The v2 rewrite does NOT use the v1 MAID manifest workflow.** Reason: we are fundamentally restructuring the manifest system itself. Instead:

- Write tests first (TDD), following `docs/unit-testing-rules.md`
- Implement to pass tests
- Use `pytest` directly for test execution
- Use standard git commits (no manifest validation during rewrite)
- Once the v2 system is self-hosting, switch to using v2 manifests

---

## Session State

**Current Phase:** Phase 6 - Integration & Ecosystem
**Current Task:** Phase 6, Task 6.1
**Notes:** Phase 5 (Features) completed and spec-aligned. 68 Phase 5 tests + 4636 prior tests = 4704 total, all passing.

```
Last working on: Phase 5 Features - spec alignment pass
Files created/modified (Phase 5 final state):
  maid_runner/core/snapshot.py (generate_snapshot, generate_system_snapshot, save_snapshot, generate_test_stub)
  maid_runner/graph/builder_v2.py (GraphBuilder - _v2 suffix: conflicts with v1 builder.py)
  maid_runner/graph/query_v2.py (GraphQuery - _v2 suffix: conflicts with v1 query.py)
  maid_runner/coherence/engine.py (CoherenceEngine - spec path, no v1 conflict)
  maid_runner/coherence/result_v2.py (CoherenceIssue, CoherenceResult - _v2 suffix: conflicts with v1 result.py)
  maid_runner/coherence/checks/base.py (BaseCheck ABC, get_checks, get_default_check_classes)
  maid_runner/coherence/checks/duplicate.py (DuplicateCheck)
  maid_runner/coherence/checks/signature.py (SignatureCheck)
  maid_runner/coherence/checks/naming.py (NamingCheck)
  maid_runner/coherence/checks/boundary.py (ModuleBoundaryCheck - ported from v1)
  maid_runner/coherence/checks/dependency.py (DependencyCheck - ported from v1)
  maid_runner/coherence/checks/pattern.py (PatternCheck - ported from v1)
  maid_runner/coherence/checks/constraint.py (ConstraintCheck - ported from v1)
  tests/core/test_snapshot.py (17 tests)
  tests/graph/test_graph_v2.py (16 tests)
  tests/coherence/test_coherence_v2.py (36 tests)
Tests status: 68 Phase 5 tests + 4636 prior tests = 4704 total
V1 code fully preserved. _v2 suffixes used ONLY where v1 files exist with same name.
Note: pyproject.toml entry point still points to old cli/main.py - switched in Phase 7.
Blockers: none
```

---

## Phase 1: Foundation

**Status:** Complete
**Spec docs:** [03-data-types.md](03-data-types.md), [04-core-manifest.md](04-core-manifest.md), [13-backward-compatibility.md](13-backward-compatibility.md)

### Tasks

- [x] **1.1** Create package structure directories
  ```
  mkdir -p maid_runner/core maid_runner/compat maid_runner/schemas
  mkdir -p tests/core tests/compat tests/fixtures/manifests/v2 tests/fixtures/manifests/v1
  mkdir -p tests/fixtures/source/python tests/fixtures/source/typescript tests/fixtures/source/svelte
  ```

- [x] **1.2** Create `maid_runner/core/types.py` with all enums and dataclasses
  - All types from [03-data-types.md](03-data-types.md): ArtifactKind, TaskType, ValidationMode, FileMode, ArgSpec, ArtifactSpec, FileSpec, DeleteSpec, Manifest
  - Write tests first: `tests/core/test_types.py`
  - Test: frozen dataclasses, merge_key(), qualified_name, is_private, all_file_specs, etc.

- [x] **1.3** Create `maid_runner/core/result.py` with all result types
  - ErrorCode, Severity, Location, ValidationError, FileTrackingStatus, FileTrackingEntry, FileTrackingReport, ValidationResult, BatchValidationResult, TestRunResult, BatchTestResult
  - Write tests: `tests/core/test_result.py`
  - Test: to_dict(), to_json() serialization, success property

- [x] **1.4** Create `maid_runner/schemas/manifest.v2.schema.json`
  - JSON Schema for v2 YAML manifests per [02-manifest-schema-v2.md](02-manifest-schema-v2.md)
  - Test with sample manifests

- [x] **1.5** Copy `maid_runner/schemas/manifest.v1.schema.json` from current `validators/schemas/manifest.schema.json`

- [x] **1.6** Create `maid_runner/core/manifest.py`
  - load_manifest(), save_manifest(), validate_manifest_schema(), slug_from_path()
  - Write tests first: `tests/core/test_manifest.py`
  - Use golden tests from [15-golden-tests.md](15-golden-tests.md)

- [x] **1.7** Create test fixture manifests
  - `tests/fixtures/manifests/v2/simple-feature.manifest.yaml`
  - `tests/fixtures/manifests/v2/multi-file.manifest.yaml`
  - `tests/fixtures/manifests/v2/with-supersession.manifest.yaml`
  - `tests/fixtures/manifests/v2/deletion.manifest.yaml`
  - `tests/fixtures/manifests/v2/snapshot.manifest.yaml`
  - Copy some v1 manifests from current `manifests/` to `tests/fixtures/manifests/v1/`

- [x] **1.8** Create `maid_runner/compat/v1_loader.py`
  - is_v1_manifest(), convert_v1_to_v2(), convert_v1_file()
  - Write tests: `tests/compat/test_v1_loader.py`
  - Test with actual v1 manifests from this project

- [x] **1.9** Create `maid_runner/core/config.py`
  - MaidConfig loading from .maidrc.yaml
  - Write tests: `tests/core/test_config.py`

### Phase 1 Verification

```bash
# All phase 1 tests pass
uv run pytest tests/core/test_types.py tests/core/test_result.py tests/core/test_manifest.py tests/core/test_config.py tests/compat/test_v1_loader.py -v

# Type checking passes
uv run mypy maid_runner/core/types.py maid_runner/core/result.py maid_runner/core/manifest.py maid_runner/compat/v1_loader.py

# Existing tests still pass (old code untouched)
uv run pytest tests/ -v --ignore=tests/core --ignore=tests/compat --ignore=tests/validators --ignore=tests/graph --ignore=tests/coherence --ignore=tests/cli --ignore=tests/integration
```

---

## Phase 2: Validation Engine

**Status:** Complete
**Spec docs:** [04-core-manifest.md](04-core-manifest.md), [05-core-validation.md](05-core-validation.md), [05b-core-test-runner.md](05b-core-test-runner.md)

### Tasks

- [x] **2.1** Create `maid_runner/core/chain.py` - ManifestChain
  - Write tests first: `tests/core/test_chain.py`
  - Test: discovery, supersession, merge, active/superseded sets, file modes
  - Use golden tests from [15-golden-tests.md](15-golden-tests.md)

- [x] **2.2** Create `maid_runner/core/_type_compare.py` - Type normalization
  - Port algorithms from [16-porting-reference.md](16-porting-reference.md)
  - Write tests: `tests/core/test_type_compare.py`
  - Use golden type comparison cases from [15-golden-tests.md](15-golden-tests.md)

- [x] **2.3** Create `maid_runner/core/_file_discovery.py` - Source file discovery
  - Write tests: included in `tests/core/test_validate.py`

- [x] **2.4** Create `maid_runner/core/validate.py` - ValidationEngine
  - Write tests first: `tests/core/test_validate.py`
  - Implement validate(), validate_all(), validate_behavioral(), validate_implementation()
  - Test with golden test cases from [15-golden-tests.md](15-golden-tests.md)

- [x] **2.5** Create `maid_runner/core/test_runner.py` - Test execution
  - Write tests: `tests/core/test_test_runner.py`
  - Implement run_tests(), run_manifest_tests(), batch mode

### Phase 2 Verification

```bash
uv run pytest tests/core/ -v
uv run mypy maid_runner/core/
```

---

## Phase 3: Validators (Can Parallel with Phase 2)

**Status:** Complete
**Spec docs:** [06-validators.md](06-validators.md)

### Tasks

- [x] **3.1** Create `maid_runner/validators/base.py` - BaseValidator ABC, FoundArtifact, CollectionResult
  - Write tests: `tests/validators/test_base.py`

- [x] **3.2** Create `maid_runner/validators/registry.py` - ValidatorRegistry
  - Write tests: `tests/validators/test_registry.py`
  - Test: register, get, has_validator, conditional import, UnsupportedLanguageError

- [x] **3.3** Create `maid_runner/validators/python.py` - PythonValidator
  - Port from current `_ArtifactCollector` using [16-porting-reference.md](16-porting-reference.md)
  - Write tests first: `tests/validators/test_python.py`
  - Use golden test cases from [15-golden-tests.md](15-golden-tests.md)
  - Test ALL artifact types: class, function, method, attribute, async, enum, decorators, generics, self/cls filtering

- [x] **3.4** Create `maid_runner/validators/typescript.py` - TypeScriptValidator
  - Port from current `typescript_validator.py` using [16-porting-reference.md](16-porting-reference.md)
  - Write tests first: `tests/validators/test_typescript.py`
  - Use golden test cases from [15-golden-tests.md](15-golden-tests.md)

- [x] **3.5** Create `maid_runner/validators/svelte.py` - SvelteValidator
  - Write tests: `tests/validators/test_svelte.py`

### Phase 3 Verification

```bash
uv run pytest tests/validators/ -v
uv run mypy maid_runner/validators/
```

---

## Phase 4: CLI Rewrite

**Status:** Complete
**Spec docs:** [09-cli.md](09-cli.md)

### Tasks

- [x] **4.1** Create `maid_runner/cli/commands/_main.py` - Entry point and argument parser
  - Note: Created as `cli/commands/_main.py` to avoid modifying existing `cli/main.py` (preserved for Phase 7)
- [x] **4.2** Create `maid_runner/cli/commands/_format.py` - Output formatters
  - Note: Created as `cli/commands/_format.py` for same reason
- [x] **4.3** Create `maid_runner/cli/commands/validate.py`
- [x] **4.4** Create `maid_runner/cli/commands/test.py`
- [x] **4.5** Create `maid_runner/cli/commands/snapshot.py`
- [x] **4.6** Create `maid_runner/cli/commands/init.py`
- [x] **4.7** Create `maid_runner/cli/commands/manifest.py`
- [x] **4.8** Create `maid_runner/cli/commands/files.py`
- [x] **4.9** Create `maid_runner/cli/commands/graph.py`
- [x] **4.10** Create `maid_runner/cli/commands/coherence.py`
- [x] **4.11** Create `maid_runner/cli/commands/schema.py`
- [x] **4.12** Create `maid_runner/cli/commands/howto.py`
- [x] **4.13** Write CLI tests: `tests/cli/` (76 tests across 9 test files)
- [x] **4.14** Update `maid_runner/__init__.py` with public API exports per [10-public-api.md](10-public-api.md)
  - Both `maid_runner/__init__.py` and `maid_runner/core/__init__.py` export v2 API
  - v1 exports preserved alongside v2 (both `from maid_runner import validate_schema` and `from maid_runner import validate` work)
- [x] **4.15** Verify v2 CLI works end-to-end (all 12 subcommands registered, validate/test functional)

### Phase 4 Verification

```bash
uv run pytest tests/cli/ -v
uv run maid validate --help
uv run maid test --help
uv run maid snapshot --help
```

---

## Phase 5: Features

**Status:** Complete
**Spec docs:** [05a-core-snapshot.md](05a-core-snapshot.md), [07-graph-module.md](07-graph-module.md), [08-coherence-module.md](08-coherence-module.md)

### Tasks

- [x] **5.1** Create `maid_runner/core/snapshot.py`
  - Write tests: `tests/core/test_snapshot.py` (17 tests)
- [x] **5.2** Port `maid_runner/graph/` module
  - Created `graph/builder_v2.py` (GraphBuilder) and `graph/query_v2.py` (GraphQuery)
  - Write tests: `tests/graph/test_graph_v2.py` (16 tests)
  - V1 builder.py/query.py preserved unchanged
- [x] **5.3** Port `maid_runner/coherence/` module
  - Created `coherence/engine.py` (spec path - no v1 conflict)
  - Created `coherence/result_v2.py` (_v2 suffix - conflicts with v1 result.py)
  - Split checks into spec-named individual files in `coherence/checks/`:
    `base.py`, `duplicate.py`, `signature.py`, `naming.py`,
    `boundary.py`, `dependency.py`, `pattern.py`, `constraint.py`
    (all differ from v1 filenames: `*_check.py` / `module_boundary.py`)
  - All 7 checks fully implemented (ported from v1 logic to v2 types)
  - Write tests: `tests/coherence/test_coherence_v2.py` (36 tests)
  - V1 validator.py/result.py/checks/*_check.py preserved unchanged

### Phase 5 Verification

```bash
uv run pytest tests/core/test_snapshot.py tests/graph/ tests/coherence/ -v
```

---

## Phase 6: Integration & Ecosystem

**Status:** Not started
**Spec docs:** [10-public-api.md](10-public-api.md)

### Tasks

- [ ] **6.1** Write integration tests: `tests/integration/test_full_workflow.py`
- [ ] **6.2** Write integration tests: `tests/integration/test_library_api.py`
- [ ] **6.3** Write integration tests: `tests/integration/test_backward_compat.py`
- [ ] **6.4** Update README.md with v2 examples
- [ ] **6.5** Verify public API matches [10-public-api.md](10-public-api.md)

### Phase 6 Verification

```bash
uv run pytest tests/ -v
uv run mypy maid_runner/
```

---

## Phase 7: Cleanup

**Status:** Not started
**Spec docs:** [12-migration-plan.md](12-migration-plan.md)

### Tasks

- [ ] **7.1** Remove old CLI modules (cli/validate.py, cli/test.py, cli/snapshot.py, cli/init.py, cli/_*.py)
- [ ] **7.2** Remove old validator integration code (validators/manifest_validator.py, validators/semantic_validator.py, validators/_*.py)
- [ ] **7.3** Remove old cache module
- [ ] **7.4** Remove old test files (tests/test_task_*.py, tests/_test_task_*.py)
- [ ] **7.5** Run full test suite and coverage report
- [ ] **7.6** Run linting and type checking: `make lint && make type-check`
- [ ] **7.7** Update pyproject.toml version to 2.0.0
- [ ] **7.8** Final verification: `uv run maid validate` on project's own manifests (if using v2 manifests)

### Phase 7 Verification

```bash
uv run pytest tests/ -v --cov=maid_runner --cov-report=term-missing
uv run mypy maid_runner/
uv run black --check maid_runner/ tests/
uv run ruff check maid_runner/ tests/
```
