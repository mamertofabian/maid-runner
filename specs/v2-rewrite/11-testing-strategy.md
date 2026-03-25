# MAID Runner v2 - Testing Strategy

**References:** [00-overview.md](00-overview.md), [01-architecture.md](01-architecture.md)

## Design Principles

1. **Domain-organized** - Tests mirror source structure, not task numbers
2. **Behavior-focused** - Test what the code does, not how it's implemented
3. **Minimal mocking** - Only mock I/O boundaries (file system, subprocess)
4. **Independent** - Each test file runs in isolation, no cross-file dependencies
5. **Deterministic** - Same input always produces same output, no timing-dependent tests
6. **Efficient** - Target ~30K lines of tests (down from 88K), same coverage

## Test Directory Structure

```
tests/
├── conftest.py                      # Shared fixtures (manifest builders, temp dirs)
│
├── core/                            # Tests for maid_runner/core/
│   ├── conftest.py                  # Core-specific fixtures
│   ├── test_manifest.py             # Manifest loading, parsing, schema validation
│   ├── test_chain.py                # ManifestChain resolution, merge, supersession
│   ├── test_validate.py             # ValidationEngine (behavioral + implementation)
│   ├── test_result.py               # Result types, serialization
│   ├── test_snapshot.py             # Snapshot generation
│   ├── test_config.py               # Configuration loading
│   └── test_type_compare.py         # Type normalization and comparison
│
├── validators/                      # Tests for maid_runner/validators/
│   ├── conftest.py                  # Validator-specific fixtures (sample code)
│   ├── test_registry.py             # ValidatorRegistry, registration, lookup
│   ├── test_python.py               # PythonValidator (all Python artifact detection)
│   ├── test_typescript.py           # TypeScriptValidator (all TS artifact detection)
│   └── test_svelte.py               # SvelteValidator
│
├── graph/                           # Tests for maid_runner/graph/
│   ├── test_model.py                # Node, Edge, KnowledgeGraph
│   ├── test_builder.py              # GraphBuilder
│   ├── test_query.py                # GraphQuery, QueryParser
│   └── test_export.py               # JSON, DOT, GraphML exporters
│
├── coherence/                       # Tests for maid_runner/coherence/
│   ├── test_engine.py               # CoherenceEngine
│   ├── test_duplicate_check.py      # DuplicateCheck
│   ├── test_signature_check.py      # SignatureCheck
│   ├── test_boundary_check.py       # ModuleBoundaryCheck
│   ├── test_naming_check.py         # NamingCheck
│   ├── test_dependency_check.py     # DependencyCheck
│   ├── test_pattern_check.py        # PatternCheck
│   └── test_constraint_check.py     # ConstraintCheck
│
├── compat/                          # Tests for maid_runner/compat/
│   └── test_v1_loader.py            # V1 JSON -> V2 conversion
│
├── cli/                             # Tests for maid_runner/cli/
│   ├── test_validate_cmd.py         # Validate command
│   ├── test_test_cmd.py             # Test command
│   ├── test_snapshot_cmd.py         # Snapshot command
│   ├── test_init_cmd.py             # Init command
│   ├── test_manifest_cmd.py         # Manifest create command
│   ├── test_graph_cmd.py            # Graph command
│   └── test_format.py               # Output formatters
│
├── integration/                     # End-to-end integration tests
│   ├── test_full_workflow.py         # Complete MAID workflow (create -> validate -> test)
│   ├── test_library_api.py           # Public API usage scenarios
│   ├── test_multi_language.py        # Python + TypeScript mixed project
│   └── test_backward_compat.py       # V1 manifest loading and validation
│
└── fixtures/                        # Shared test data
    ├── manifests/                   # Sample manifests for testing
    │   ├── v2/                      # V2 YAML manifests
    │   │   ├── simple-feature.manifest.yaml
    │   │   ├── multi-file.manifest.yaml
    │   │   ├── with-supersession.manifest.yaml
    │   │   ├── deletion.manifest.yaml
    │   │   ├── snapshot.manifest.yaml
    │   │   └── typescript-feature.manifest.yaml
    │   └── v1/                      # V1 JSON manifests (for compat tests)
    │       ├── task-001.manifest.json
    │       └── task-002.manifest.json
    ├── source/                      # Sample source files for validation
    │   ├── python/
    │   │   ├── simple_class.py
    │   │   ├── async_functions.py
    │   │   ├── type_aliases.py
    │   │   └── class_methods.py
    │   ├── typescript/
    │   │   ├── simple_class.ts
    │   │   ├── interfaces.ts
    │   │   ├── react_component.tsx
    │   │   └── arrow_functions.ts
    │   └── svelte/
    │       ├── component.svelte
    │       └── ts_component.svelte
    └── test_files/                  # Sample test files for behavioral validation
        ├── test_simple.py
        └── simple.test.ts
```

## Shared Fixtures (`conftest.py`)

### Root conftest.py

```python
import pytest
from pathlib import Path
from maid_runner.core.types import Manifest, FileSpec, ArtifactSpec, ArtifactKind, ArgSpec, FileMode

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with manifests/ subdirectory."""
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    return tmp_path


@pytest.fixture
def manifest_builder():
    """Builder for creating test Manifest objects."""
    return ManifestBuilder()


class ManifestBuilder:
    """Fluent builder for test Manifest objects.

    Usage:
        manifest = ManifestBuilder() \
            .with_goal("Add auth") \
            .with_create_file("src/auth.py", [
                ArtifactSpec(kind=ArtifactKind.CLASS, name="AuthService"),
            ]) \
            .build()
    """

    def __init__(self):
        self._goal = "Test goal"
        self._slug = "test-manifest"
        self._source_path = "manifests/test.manifest.yaml"
        self._validate = (("pytest", "tests/test.py", "-v"),)
        self._files_create = []
        self._files_edit = []
        self._files_read = []
        self._files_delete = []
        self._supersedes = ()
        self._task_type = None

    def with_goal(self, goal: str) -> "ManifestBuilder":
        self._goal = goal
        return self

    def with_slug(self, slug: str) -> "ManifestBuilder":
        self._slug = slug
        return self

    def with_create_file(self, path: str, artifacts: list[ArtifactSpec]) -> "ManifestBuilder":
        self._files_create.append(FileSpec(
            path=path,
            artifacts=tuple(artifacts),
            mode=FileMode.CREATE,
        ))
        return self

    def with_edit_file(self, path: str, artifacts: list[ArtifactSpec]) -> "ManifestBuilder":
        self._files_edit.append(FileSpec(
            path=path,
            artifacts=tuple(artifacts),
            mode=FileMode.EDIT,
        ))
        return self

    def with_read_file(self, path: str) -> "ManifestBuilder":
        self._files_read.append(path)
        return self

    def with_supersedes(self, *slugs: str) -> "ManifestBuilder":
        self._supersedes = slugs
        return self

    def with_validate(self, *commands: tuple[str, ...]) -> "ManifestBuilder":
        self._validate = commands
        return self

    def build(self) -> Manifest:
        return Manifest(
            slug=self._slug,
            source_path=self._source_path,
            goal=self._goal,
            validate_commands=self._validate,
            files_create=tuple(self._files_create),
            files_edit=tuple(self._files_edit),
            files_read=tuple(self._files_read),
            files_delete=tuple(self._files_delete),
            supersedes=self._supersedes,
            task_type=self._task_type,
        )


def make_artifact(
    kind: ArtifactKind = ArtifactKind.FUNCTION,
    name: str = "example",
    of: str | None = None,
    args: list[tuple[str, str | None]] | None = None,
    returns: str | None = None,
) -> ArtifactSpec:
    """Quick helper for creating ArtifactSpec in tests."""
    arg_specs = tuple(ArgSpec(name=n, type=t) for n, t in (args or []))
    return ArtifactSpec(kind=kind, name=name, of=of, args=arg_specs, returns=returns)
```

## Test Patterns

### Pattern 1: Manifest Loading Tests (`core/test_manifest.py`)

```python
class TestLoadManifest:
    """Tests for load_manifest()."""

    def test_load_v2_yaml(self, tmp_path):
        """Load a valid v2 YAML manifest."""
        manifest_path = tmp_path / "test.manifest.yaml"
        manifest_path.write_text("""
schema: "2"
goal: "Add feature"
files:
  create:
    - path: src/feature.py
      artifacts:
        - kind: class
          name: Feature
validate:
  - pytest tests/test_feature.py -v
""")
        manifest = load_manifest(manifest_path)
        assert manifest.goal == "Add feature"
        assert manifest.schema_version == "2"
        assert len(manifest.files_create) == 1
        assert manifest.files_create[0].artifacts[0].name == "Feature"

    def test_load_v1_json(self, tmp_path):
        """Load a v1 JSON manifest (auto-converted to v2)."""
        # ...

    def test_load_nonexistent_file(self):
        """Raises ManifestLoadError for missing file."""
        with pytest.raises(ManifestLoadError):
            load_manifest("nonexistent.manifest.yaml")

    def test_schema_validation_error(self, tmp_path):
        """Raises ManifestSchemaError for invalid manifest."""
        manifest_path = tmp_path / "bad.manifest.yaml"
        manifest_path.write_text("schema: '2'\n# missing goal")
        with pytest.raises(ManifestSchemaError):
            load_manifest(manifest_path)
```

### Pattern 2: Validation Engine Tests (`core/test_validate.py`)

```python
class TestImplementationValidation:
    """Tests for implementation validation mode."""

    def test_all_artifacts_present(self, tmp_project, manifest_builder):
        """Pass when all declared artifacts exist in code."""
        # Create source file
        src = tmp_project / "src" / "feature.py"
        src.parent.mkdir(parents=True)
        src.write_text("class Feature:\n    def do_thing(self): pass\n")

        # Create manifest
        manifest = manifest_builder \
            .with_create_file("src/feature.py", [
                make_artifact(ArtifactKind.CLASS, "Feature"),
                make_artifact(ArtifactKind.METHOD, "do_thing", of="Feature"),
            ]) \
            .build()

        engine = ValidationEngine(project_root=tmp_project)
        errors = engine.validate_implementation(manifest)
        assert errors == []

    def test_missing_artifact(self, tmp_project, manifest_builder):
        """Fail when declared artifact is missing from code."""
        src = tmp_project / "src" / "feature.py"
        src.parent.mkdir(parents=True)
        src.write_text("class Feature: pass\n")

        manifest = manifest_builder \
            .with_create_file("src/feature.py", [
                make_artifact(ArtifactKind.CLASS, "Feature"),
                make_artifact(ArtifactKind.METHOD, "do_thing", of="Feature"),
            ]) \
            .build()

        engine = ValidationEngine(project_root=tmp_project)
        errors = engine.validate_implementation(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.ARTIFACT_NOT_DEFINED
        assert "do_thing" in errors[0].message

    def test_strict_mode_rejects_unexpected(self, tmp_project, manifest_builder):
        """Strict mode (create) rejects undeclared public artifacts."""
        # ...

    def test_permissive_mode_allows_extra(self, tmp_project, manifest_builder):
        """Permissive mode (edit) allows additional public artifacts."""
        # ...
```

### Pattern 3: Validator Tests (`validators/test_python.py`)

```python
class TestPythonImplementationCollection:
    """Tests for PythonValidator.collect_implementation_artifacts()."""

    def test_class_detection(self):
        source = "class MyClass:\n    pass\n"
        result = PythonValidator().collect_implementation_artifacts(source, "test.py")
        assert len(result.artifacts) == 1
        assert result.artifacts[0].kind == ArtifactKind.CLASS
        assert result.artifacts[0].name == "MyClass"

    def test_method_with_self_filtered(self):
        source = "class Foo:\n    def bar(self, x: int) -> str: pass\n"
        result = PythonValidator().collect_implementation_artifacts(source, "test.py")
        method = [a for a in result.artifacts if a.name == "bar"][0]
        assert method.kind == ArtifactKind.METHOD
        assert method.of == "Foo"
        assert len(method.args) == 1  # self filtered
        assert method.args[0].name == "x"

    def test_async_function(self):
        source = "async def fetch(): pass\n"
        result = PythonValidator().collect_implementation_artifacts(source, "test.py")
        assert result.artifacts[0].is_async is True

    # ... comprehensive tests for all Python constructs
```

### Pattern 4: Integration Tests (`integration/test_full_workflow.py`)

```python
class TestFullWorkflow:
    """End-to-end tests simulating complete MAID workflow."""

    def test_create_validate_pass(self, tmp_project):
        """Full workflow: create manifest, write code, validate passes."""
        # 1. Create manifest file
        manifest_yaml = tmp_project / "manifests" / "add-greet.manifest.yaml"
        manifest_yaml.write_text("""
schema: "2"
goal: "Add greeting function"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
          returns: str
validate:
  - pytest tests/test_greet.py -v
""")

        # 2. Create source file matching the manifest
        src = tmp_project / "src" / "greet.py"
        src.parent.mkdir(parents=True)
        src.write_text("def greet(name: str) -> str:\n    return f'Hello, {name}!'\n")

        # 3. Validate
        result = validate(str(manifest_yaml), project_root=str(tmp_project))
        assert result.success
        assert result.errors == []

    def test_multi_file_manifest(self, tmp_project):
        """Multi-file manifest validates artifacts across files."""
        # ...

    def test_manifest_chain_merge(self, tmp_project):
        """Chain merges artifacts from multiple manifests for same file."""
        # ...

    def test_supersession_excludes_old(self, tmp_project):
        """Superseded manifests are excluded from validation."""
        # ...
```

## What Each Test File Covers

### Core Tests

| Test File | Source Module | Key Behaviors Tested |
|-----------|--------------|---------------------|
| `test_manifest.py` | `core/manifest.py` | YAML loading, JSON loading, schema validation, slug extraction, v1 auto-detection, error handling |
| `test_chain.py` | `core/chain.py` | Discovery, supersession resolution, active/superseded sets, artifact merge, file mode resolution, cycle detection, cache invalidation |
| `test_validate.py` | `core/validate.py` | Behavioral mode, implementation mode, strict/permissive, type comparison, absent status, file tracking, batch validation |
| `test_result.py` | `core/result.py` | Serialization to dict/JSON, error code coverage, severity handling |
| `test_snapshot.py` | `core/snapshot.py` | Python snapshot, TypeScript snapshot, test stub generation, multi-language |
| `test_type_compare.py` | `core/_type_compare.py` | Optional/Union normalization, PEP 585, generic types, edge cases |

### Validator Tests

| Test File | Source Module | Key Behaviors Tested |
|-----------|--------------|---------------------|
| `test_registry.py` | `validators/__init__.py` | Registration, lookup by extension, missing validator error, clear, conditional import |
| `test_python.py` | `validators/python.py` | Classes, functions, methods, async, decorators, type annotations, module attrs, class attrs, self/cls filtering, generics, ABC, enum, nested classes, behavioral refs |
| `test_typescript.py` | `validators/typescript.py` | Classes, interfaces, types, enums, namespaces, arrow functions, JSX/TSX, methods, generators, private filtering, variable-class mapping, object property exclusion |
| `test_svelte.py` | `validators/svelte.py` | Script extraction, delegation to TS validator, lang detection |

### Graph Tests

| Test File | Source Module | Key Behaviors Tested |
|-----------|--------------|---------------------|
| `test_model.py` | `graph/model.py` | Node CRUD, edge CRUD, adjacency queries, duplicate handling |
| `test_builder.py` | `graph/builder.py` | Full graph construction from chain, node/edge counts, supersession edges |
| `test_query.py` | `graph/query.py` | Node search, cycle detection, dependency analysis, impact analysis, natural language queries |
| `test_export.py` | `graph/export.py` | JSON structure, DOT format, GraphML structure |

### Coherence Tests

| Test File | Source Module | Key Behaviors Tested |
|-----------|--------------|---------------------|
| `test_engine.py` | `coherence/engine.py` | Check orchestration, result aggregation, check filtering |
| `test_*_check.py` | `coherence/checks/*.py` | Each check's detection logic, severity, suggestions |

### CLI Tests

| Test File | Source Module | Key Behaviors Tested |
|-----------|--------------|---------------------|
| `test_validate_cmd.py` | `cli/commands/validate.py` | Argument parsing, exit codes, JSON output, single vs batch |
| `test_test_cmd.py` | `cli/commands/test.py` | Test execution, fail-fast, batch mode |
| `test_snapshot_cmd.py` | `cli/commands/snapshot.py` | Snapshot generation, dry-run, output options |
| `test_format.py` | `cli/format.py` | Text formatting, JSON formatting, quiet mode |

## Migration from Current Tests

### Mapping Strategy

The current 130+ test files map to the new structure:

```
# Current -> New (many-to-one mapping)

test_validate_schema.py                    -> core/test_manifest.py
test_task_003_behavioral_validation.py     -> core/test_validate.py (behavioral section)
test_task_004_behavioral_test_integration  -> core/test_validate.py (behavioral section)
test_task_005_type_validation.py           -> core/test_type_compare.py
test_task_006_artifact_kind_metadata.py    -> validators/test_python.py
test_task_007_type_definitions_module.py   -> core/test_result.py (types section)
test_task_008_snapshot_generator.py        -> core/test_snapshot.py
test_task_022_validate_manifest_dir.py     -> core/test_chain.py
test_task_025_fix_cls_parameter.py         -> validators/test_python.py
test_task_028_file_tracking_validation.py  -> core/test_validate.py (tracking section)
test_task_053_typescript_validator.py      -> validators/test_typescript.py
test_task_086_svelte_validator.py          -> validators/test_svelte.py
test_task_101-119 (graph tasks)            -> graph/test_*.py
test_task_126-141 (coherence tasks)        -> coherence/test_*.py

# Integration tests consolidate workflow tests
test_task_010_type_validation_integration  -> integration/test_full_workflow.py
test_task_118_cli_main_integration.py      -> integration/test_library_api.py
```

### Test Migration Process

1. **Extract test cases by behavior** - Read each existing test, classify by what behavior it tests
2. **Group into domain files** - Place in the corresponding new test file
3. **Deduplicate** - Many tests in the current suite overlap; keep the most comprehensive version
4. **Update imports** - Change from old module paths to new public API
5. **Replace task-specific fixtures** - Use shared ManifestBuilder and helpers
6. **Verify coverage** - Run coverage report to ensure no behaviors lost

### Coverage Targets

| Package | Line Coverage Target | Branch Coverage Target |
|---------|---------------------|----------------------|
| core/ | 95% | 90% |
| validators/ | 90% | 85% |
| graph/ | 90% | 85% |
| coherence/ | 85% | 80% |
| cli/ | 80% | 75% |
| compat/ | 95% | 90% |

## Testing Tools

```toml
# pyproject.toml
[dependency-groups]
dev = [
    "pytest>=8.4",
    "pytest-cov>=7.0",
    "black>=25.1",
    "ruff>=0.13",
    "mypy>=1.15",
]
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific domain
uv run pytest tests/core/ -v
uv run pytest tests/validators/ -v

# Run with coverage
uv run pytest tests/ --cov=maid_runner --cov-report=term-missing

# Run integration tests only
uv run pytest tests/integration/ -v
```
