"""Characterization tests for ValidationEngine orchestration results."""

from __future__ import annotations

import json
from pathlib import Path

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import (
    BatchValidationResult,
)
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _write_manifest(project: Path, name: str, content: str) -> Path:
    return _write(project / "manifests" / name, content)


def _write_clean_project(project: Path) -> None:
    _write(
        project / "src" / "alpha.py",
        "def alpha():\n    return 'alpha'\n",
    )
    _write(
        project / "src" / "beta.py",
        "def beta():\n    return 'beta'\n",
    )
    _write(
        project / "tests" / "test_alpha.py",
        "from src.alpha import alpha\n\n"
        "def test_alpha():\n"
        "    assert alpha() == 'alpha'\n",
    )
    _write(
        project / "tests" / "test_beta.py",
        "from src.beta import beta\n\n"
        "def test_beta():\n"
        "    assert beta() == 'beta'\n",
    )
    _write_manifest(
        project,
        "add-alpha.manifest.yaml",
        """schema: "2"
goal: "Add alpha"
type: feature
created: "2026-01-01"
files:
  create:
    - path: src/alpha.py
      artifacts:
        - kind: function
          name: alpha
  read:
    - tests/test_alpha.py
validate:
  - pytest tests/test_alpha.py -q
""",
    )
    _write_manifest(
        project,
        "add-beta.manifest.yaml",
        """schema: "2"
goal: "Add beta"
type: feature
created: "2026-01-02"
files:
  create:
    - path: src/beta.py
      artifacts:
        - kind: function
          name: beta
  read:
    - tests/test_beta.py
validate:
  - pytest tests/test_beta.py -q
""",
    )


def _batch_to_dict_without_durations(result: BatchValidationResult) -> dict:
    data = result.to_dict()
    data["duration_ms"] = None
    for manifest_result in data["results"]:
        manifest_result["duration_ms"] = None
    return data


def _validation_to_dict_without_duration(result) -> dict:
    data = result.to_dict()
    data["duration_ms"] = None
    return data


def test_validate_all_locks_success_result_shape_for_clean_manifests(
    tmp_path: Path,
) -> None:
    _write_clean_project(tmp_path)
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert _batch_to_dict_without_durations(result) == {
        "success": True,
        "total": 2,
        "passed": 2,
        "failed": 0,
        "skipped": 0,
        "chain_errors": [],
        "results": [
            {
                "success": True,
                "manifest": "add-alpha",
                "manifest_path": str(
                    tmp_path / "manifests" / "add-alpha.manifest.yaml"
                ),
                "mode": "implementation",
                "errors": [],
                "warnings": [],
                "duration_ms": None,
            },
            {
                "success": True,
                "manifest": "add-beta",
                "manifest_path": str(tmp_path / "manifests" / "add-beta.manifest.yaml"),
                "mode": "implementation",
                "errors": [],
                "warnings": [],
                "duration_ms": None,
            },
        ],
        "duration_ms": None,
    }


def test_validate_all_locks_supersession_warning_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "replacement.py",
        "def replacement():\n    return 'replacement'\n",
    )
    _write(
        tmp_path / "tests" / "test_replacement.py",
        "from src.replacement import replacement\n\n"
        "def test_replacement():\n"
        "    assert replacement() == 'replacement'\n",
    )
    _write_manifest(
        tmp_path,
        "replacement.manifest.yaml",
        """schema: "2"
goal: "Replace missing base"
type: feature
created: "2026-01-01"
supersedes:
  - missing-base
files:
  create:
    - path: src/replacement.py
      artifacts:
        - kind: function
          name: replacement
  read:
    - tests/test_replacement.py
validate:
  - pytest tests/test_replacement.py -q
""",
    )
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert _batch_to_dict_without_durations(result) == {
        "success": True,
        "total": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "chain_errors": [
            {
                "code": "E102",
                "message": (
                    "Manifest 'replacement' supersedes non-existent manifest "
                    "'missing-base'"
                ),
                "severity": "warning",
                "location": {
                    "file": str(tmp_path / "manifests" / "replacement.manifest.yaml"),
                    "line": None,
                    "column": None,
                },
            }
        ],
        "results": [
            {
                "success": True,
                "manifest": "replacement",
                "manifest_path": str(
                    tmp_path / "manifests" / "replacement.manifest.yaml"
                ),
                "mode": "implementation",
                "errors": [],
                "warnings": [],
                "duration_ms": None,
            }
        ],
        "duration_ms": None,
    }


def test_validate_all_locks_error_codes_for_missing_manifest_dir(
    tmp_path: Path,
) -> None:
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate_all("missing-manifests", allow_empty=False)

    assert isinstance(result.duration_ms, float)
    assert result.duration_ms >= 0
    assert _batch_to_dict_without_durations(result) == {
        "success": False,
        "total": 0,
        "passed": 0,
        "failed": 1,
        "skipped": 0,
        "chain_errors": [
            {
                "code": "E112",
                "message": (
                    f"Manifest directory not found: {tmp_path / 'missing-manifests'}"
                ),
                "severity": "error",
                "location": {
                    "file": str(tmp_path / "missing-manifests"),
                    "line": None,
                    "column": None,
                },
                "suggestion": (
                    "Pass --allow-empty only when an empty manifest set is intentional."
                ),
            }
        ],
        "results": [],
        "duration_ms": None,
    }


def test_validate_locks_schema_error_shape_for_bad_manifest(tmp_path: Path) -> None:
    bad_manifest = _write(
        tmp_path / "bad.manifest.yaml",
        """schema: "2"
files:
  create:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
validate:
  - pytest tests/test_widget.py -q
""",
    )
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate(bad_manifest, mode=ValidationMode.IMPLEMENTATION)

    assert result.duration_ms is None
    assert result.to_dict() == {
        "success": False,
        "manifest": "unknown",
        "manifest_path": str(bad_manifest),
        "mode": "implementation",
        "errors": [
            {
                "code": "E004",
                "message": (
                    f"Schema validation failed for {bad_manifest}: "
                    "'goal' is a required property"
                ),
                "severity": "error",
            }
        ],
        "warnings": [],
    }
    assert json.loads(result.to_json()) == result.to_dict()


def test_validate_behavioral_locks_coverage_error_for_uncovered_artifact(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
type: feature
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -q
""",
    )
    _write(tmp_path / "src" / "widget.py", "def render():\n    return 'widget'\n")
    _write(
        tmp_path / "tests" / "test_widget.py",
        "def test_placeholder():\n    assert True\n",
    )
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert result.success is False
    assert result.warnings == []
    assert [error.to_dict() for error in result.errors] == [
        {
            "code": "E200",
            "message": "Artifact 'render' not used in any test file",
            "severity": "error",
            "location": {
                "file": "src/widget.py",
                "line": None,
                "column": None,
            },
        }
    ]


def test_validate_behavioral_direct_locks_error_list_for_uncovered_artifact(
    tmp_path: Path,
) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
type: feature
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -q
""",
    )
    _write(tmp_path / "src" / "widget.py", "def render():\n    return 'widget'\n")
    _write(
        tmp_path / "tests" / "test_widget.py",
        "def test_placeholder():\n    assert True\n",
    )
    manifest = load_manifest(manifest_path)
    engine = ValidationEngine(project_root=tmp_path)

    errors = engine.validate_behavioral(manifest)

    assert [error.to_dict() for error in errors] == [
        {
            "code": "E200",
            "message": "Artifact 'render' not used in any test file",
            "severity": "error",
            "location": {
                "file": "src/widget.py",
                "line": None,
                "column": None,
            },
        }
    ]


def test_check_test_coverage_locks_no_test_files_error(tmp_path: Path) -> None:
    manifest_path = _write_manifest(
        tmp_path,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
type: feature
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
validate:
  - make check
""",
    )
    _write(tmp_path / "src" / "widget.py", "def render():\n    return 'widget'\n")
    engine = ValidationEngine(project_root=tmp_path)

    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert _validation_to_dict_without_duration(result) == {
        "success": False,
        "manifest": "add-widget",
        "manifest_path": str(manifest_path),
        "mode": "implementation",
        "errors": [
            {
                "code": "E220",
                "message": (
                    "Manifest 'add-widget' declares public artifacts but has "
                    "no test files — add test file paths to files.read or "
                    "validate commands"
                ),
                "severity": "error",
                "suggestion": (
                    "Add test files to the 'files.read' section or reference "
                    "them in 'validate' commands (e.g., pytest tests/test_foo.py -v)"
                ),
            }
        ],
        "warnings": [],
        "duration_ms": None,
    }


def test_validate_removed_artifacts_locks_still_present_error(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src" / "greet.py",
        "class Greeter:\n"
        "    def old_method(self) -> None:\n"
        "        pass\n\n"
        "    def new_method(self) -> None:\n"
        "        pass\n",
    )
    manifest_path = _write(
        tmp_path / "remove-old.manifest.yaml",
        """schema: "2"
goal: "Remove old method"
type: refactor
removed_artifacts:
  - kind: method
    name: old_method
    of: Greeter
    file: src/greet.py
    reason: "deprecated"
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: method
          name: new_method
          of: Greeter
validate:
  - pytest tests/test_greet.py -q
""",
    )
    manifest = load_manifest(manifest_path)
    engine = ValidationEngine(project_root=tmp_path)

    errors = engine.validate_removed_artifacts(manifest)

    assert [error.to_dict() for error in errors] == [
        {
            "code": "E311",
            "message": (
                "Manifest declares 'old_method' as removed from src/greet.py "
                "but the symbol is still defined in the source"
            ),
            "severity": "error",
            "location": {
                "file": "src/greet.py",
                "line": 2,
                "column": None,
            },
            "suggestion": (
                "Remove the symbol from the source, or drop the "
                "removed_artifacts entry if removal was not intended."
            ),
        }
    ]


def test_validate_removed_artifacts_locks_method_requires_of(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "src" / "greet.py",
        "class Greeter:\n" "    def old_method(self) -> None:\n" "        pass\n",
    )
    manifest_path = _write(
        tmp_path / "remove-old.manifest.yaml",
        """schema: "2"
goal: "Remove old method"
type: refactor
removed_artifacts:
  - kind: method
    name: old_method
    file: src/greet.py
    reason: "deprecated"
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: method
          name: new_method
          of: Greeter
validate:
  - pytest tests/test_greet.py -q
""",
    )
    manifest = load_manifest(manifest_path)
    engine = ValidationEngine(project_root=tmp_path)

    errors = engine.validate_removed_artifacts(manifest)

    assert [error.to_dict() for error in errors] == [
        {
            "code": "E311",
            "message": (
                "Cannot verify removal of 'old_method' (method) from "
                "'src/greet.py': 'of' (owner class/interface) is required "
                "for method entries"
            ),
            "severity": "error",
            "location": {
                "file": "src/greet.py",
                "line": None,
                "column": None,
            },
            "suggestion": (
                "Add `of: <OwnerClass>` to the removed_artifacts entry "
                "so the verifier can match the qualified member name."
            ),
        }
    ]


def test_validate_all_json_output_is_stable_across_runs(tmp_path: Path) -> None:
    _write_clean_project(tmp_path)
    engine = ValidationEngine(project_root=tmp_path)

    first = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)
    second = engine.validate_all(mode=ValidationMode.IMPLEMENTATION)

    assert isinstance(first, BatchValidationResult)
    assert _batch_to_dict_without_durations(first) == _batch_to_dict_without_durations(
        second
    )
    assert json.dumps(_batch_to_dict_without_durations(first), sort_keys=True) == (
        json.dumps(_batch_to_dict_without_durations(second), sort_keys=True)
    )
