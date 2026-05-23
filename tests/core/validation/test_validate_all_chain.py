"""Focused characterization tests for validate_all manifest-chain behavior."""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine, validate_all


@pytest.fixture()
def project(tmp_path):
    """Create a temporary project directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def write_manifest(project_dir, name, content):
    path = project_dir / "manifests" / name
    path.write_text(content)
    return path


def write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def write_test(project_dir, rel_path, module, artifact_names):
    imports = ", ".join(artifact_names)
    assertions = "\n".join(
        f"    assert {artifact_name} is not None" for artifact_name in artifact_names
    )
    write_source(
        project_dir,
        rel_path,
        f"from {module} import {imports}\n\n"
        f"def test_declared_artifacts_exist():\n{assertions}\n",
    )


def batch_result_without_durations(result):
    data = result.to_dict()
    data["duration_ms"] = None
    for manifest_result in data["results"]:
        manifest_result["duration_ms"] = None
    return data


def test_validate_all_validates_active_manifests_and_skips_superseded(project):
    write_manifest(
        project,
        "old-greet.manifest.yaml",
        """schema: "2"
goal: "Old greet"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/old_greet.py
      artifacts:
        - kind: function
          name: old_greet
  read:
    - tests/test_old_greet.py
validate:
  - pytest tests/test_old_greet.py -v
""",
    )
    write_manifest(
        project,
        "new-greet.manifest.yaml",
        """schema: "2"
goal: "New greet"
type: feature
created: "2026-01-02"
supersedes:
  - old-greet
files:
  create:
    - path: src/new_greet.py
      artifacts:
        - kind: function
          name: new_greet
  read:
    - tests/test_new_greet.py
validate:
  - pytest tests/test_new_greet.py -v
""",
    )
    write_source(project, "src/old_greet.py", "def old_greet():\n    return 'old'\n")
    write_source(project, "src/new_greet.py", "def new_greet():\n    return 'new'\n")
    write_test(project, "tests/test_old_greet.py", "src.old_greet", ["old_greet"])
    write_test(project, "tests/test_new_greet.py", "src.new_greet", ["new_greet"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert result.total_manifests == 2
    assert result.passed == 1
    assert result.failed == 0
    assert result.skipped == 1
    assert [manifest_result.manifest_slug for manifest_result in result.results] == [
        "new-greet"
    ]


def test_validate_all_reports_invalid_manifest_as_chain_error(project):
    write_manifest(
        project,
        "good.manifest.yaml",
        """schema: "2"
goal: "Good"
files:
  create:
    - path: src/good.py
      artifacts:
        - kind: function
          name: good
  read:
    - tests/test_good.py
validate:
  - pytest tests/test_good.py -v
""",
    )
    write_manifest(
        project,
        "bad.manifest.yaml",
        """schema: "2"
goal: "Bad"
files:
  create:
    - path: src/bad.py
validate:
  - pytest
""",
    )
    write_source(project, "src/good.py", "def good():\n    return 'good'\n")
    write_test(project, "tests/test_good.py", "src.good", ["good"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert result.passed == 1
    assert result.failed == 0
    assert len(result.results) == 1
    assert any(
        error.code == ErrorCode.SCHEMA_VALIDATION_ERROR for error in result.chain_errors
    )


def test_validate_all_missing_manifest_directory_fails_by_default(tmp_path):
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate_all("missing-manifests")

    assert result.success is False
    assert result.total_manifests == 0
    assert result.failed == 1
    assert any(
        error.code == ErrorCode.EMPTY_MANIFEST_SET for error in result.chain_errors
    )


def test_validate_all_function_allows_empty_manifest_directory_when_requested(tmp_path):
    (tmp_path / "manifests").mkdir()

    result = validate_all("manifests", project_root=tmp_path, allow_empty=True)

    assert result.success is True
    assert result.total_manifests == 0
    assert result.passed == 0
    assert result.failed == 0
    assert result.chain_errors == []


def test_validate_all_applies_chain_strictness_to_active_manifests(project):
    write_manifest(
        project,
        "create-service.manifest.yaml",
        """schema: "2"
goal: "Create service"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: func_a
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    write_manifest(
        project,
        "add-func-b.manifest.yaml",
        """schema: "2"
goal: "Add func_b"
type: feature
created: "2026-01-02"
files:
  edit:
    - path: src/service.py
      artifacts:
        - kind: function
          name: func_b
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
""",
    )
    write_source(
        project,
        "src/service.py",
        "def func_a():\n"
        "    return 'a'\n\n"
        "def func_b():\n"
        "    return 'b'\n\n"
        "def func_c():\n"
        "    return 'c'\n",
    )
    write_test(project, "tests/test_service.py", "src.service", ["func_a", "func_b"])

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert result.passed == 0
    assert result.failed == 2
    assert any(
        error.code == ErrorCode.UNEXPECTED_ARTIFACT and "func_c" in error.message
        for manifest_result in result.results
        for error in manifest_result.errors
    )


def test_validate_all_results_match_uncached_manifest_chain_run(project, monkeypatch):
    import importlib

    from maid_runner.core.chain import ManifestChain, clear_manifest_chain_cache

    validate_module = importlib.import_module("maid_runner.core.validate")

    write_manifest(
        project,
        "cache-equivalence.manifest.yaml",
        """schema: "2"
goal: "Cache equivalence"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/cache_equivalence.py
      artifacts:
        - kind: function
          name: cache_equivalence
  read:
    - tests/test_cache_equivalence.py
validate:
  - pytest tests/test_cache_equivalence.py -v
""",
    )
    write_source(
        project,
        "src/cache_equivalence.py",
        "def cache_equivalence():\n    return 'ok'\n",
    )
    write_test(
        project,
        "tests/test_cache_equivalence.py",
        "src.cache_equivalence",
        ["cache_equivalence"],
    )

    clear_manifest_chain_cache()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                validate_module,
                "_get_cached_manifest_chain_for_validate_all",
                ManifestChain,
            )
            uncached = validate_all(
                "manifests",
                project_root=project,
                mode=ValidationMode.IMPLEMENTATION,
            )

        clear_manifest_chain_cache()
        cached = validate_all(
            "manifests",
            project_root=project,
            mode=ValidationMode.IMPLEMENTATION,
        )
    finally:
        clear_manifest_chain_cache()

    assert batch_result_without_durations(cached) == batch_result_without_durations(
        uncached
    )


def test_validate_all_loads_manifest_chain_once_per_invocation(project, monkeypatch):
    import importlib

    from maid_runner.core.chain import clear_manifest_chain_cache

    chain_module = importlib.import_module("maid_runner.core.chain")

    for name in ("one", "two"):
        write_manifest(
            project,
            f"{name}.manifest.yaml",
            f"""schema: "2"
goal: "{name}"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/{name}.py
      artifacts:
        - kind: function
          name: {name}
  read:
    - tests/test_{name}.py
validate:
  - pytest tests/test_{name}.py -v
""",
        )
        write_source(project, f"src/{name}.py", f"def {name}():\n    return '{name}'\n")
        write_test(project, f"tests/test_{name}.py", f"src.{name}", [name])

    constructed = 0
    original_chain = chain_module.ManifestChain

    class CountingManifestChain(original_chain):
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(chain_module, "ManifestChain", CountingManifestChain)
    clear_manifest_chain_cache()
    try:
        validate_module = importlib.import_module("maid_runner.core.validate")
        monkeypatch.setattr(validate_module, "ManifestChain", CountingManifestChain)
        result = validate_all(
            "manifests",
            project_root=project,
            mode=ValidationMode.IMPLEMENTATION,
        )
    finally:
        clear_manifest_chain_cache()

    assert result.success is True
    assert constructed == 1


def test_validate_all_clears_manifest_chain_cache_between_invocations(
    project, monkeypatch
):
    import importlib

    from maid_runner.core.chain import clear_manifest_chain_cache

    write_manifest(
        project,
        "cache-boundary.manifest.yaml",
        """schema: "2"
goal: "Cache boundary"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/cache_boundary.py
      artifacts:
        - kind: function
          name: cache_boundary
  read:
    - tests/test_cache_boundary.py
validate:
  - pytest tests/test_cache_boundary.py -v
""",
    )
    write_source(
        project,
        "src/cache_boundary.py",
        "def cache_boundary():\n    return 'ok'\n",
    )
    write_test(
        project,
        "tests/test_cache_boundary.py",
        "src.cache_boundary",
        ["cache_boundary"],
    )

    validate_module = importlib.import_module("maid_runner.core.validate")
    constructed = 0
    original_chain = validate_module.ManifestChain

    class CountingManifestChain(original_chain):
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(validate_module, "ManifestChain", CountingManifestChain)
    clear_manifest_chain_cache()
    try:
        first = validate_all(
            "manifests",
            project_root=project,
            mode=ValidationMode.IMPLEMENTATION,
        )
        second = validate_all(
            "manifests",
            project_root=project,
            mode=ValidationMode.IMPLEMENTATION,
        )
    finally:
        clear_manifest_chain_cache()

    assert first.success is True
    assert second.success is True
    assert constructed == 2
