"""Tests for per-file implementation validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core._implementation_validation import (
    ImplementationFileValidator,
    compare_artifacts,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.types import ArtifactKind, ArtifactSpec
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir()
    return tmp_path


def _write_manifest(project: Path, content: str) -> Path:
    path = project / "manifests" / "feature.manifest.yaml"
    path.write_text(content)
    return path


def _write_source(project: Path, rel_path: str, content: str) -> None:
    path = project / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _validator(
    project: Path,
    *,
    check_stubs: bool = False,
) -> ImplementationFileValidator:
    return ImplementationFileValidator(
        project,
        ValidatorRegistry.with_builtin_validators(),
        check_stubs=check_stubs,
    )


def test_validate_file_spec_preserves_missing_file_error(project: Path) -> None:
    manifest_path = _write_manifest(
        project,
        """schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
validate:
  - pytest tests/ -v
""",
    )
    manifest = load_manifest(manifest_path)
    fs = manifest.file_spec_for("src/greet.py")
    assert fs is not None

    errors = _validator(project).validate_file_spec(fs, manifest, None)

    assert [
        (e.code, e.message, e.location.file if e.location else None) for e in errors
    ] == [
        (
            ErrorCode.FILE_SHOULD_BE_PRESENT,
            "File 'src/greet.py' not found",
            "src/greet.py",
        )
    ]


def test_validate_file_spec_preserves_stub_warning(project: Path) -> None:
    manifest_path = _write_manifest(
        project,
        """schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
validate:
  - pytest tests/ -v
""",
    )
    _write_source(project, "src/greet.py", "def greet():\n    pass\n")
    manifest = load_manifest(manifest_path)
    fs = manifest.file_spec_for("src/greet.py")
    assert fs is not None

    errors = _validator(project, check_stubs=True).validate_file_spec(
        fs,
        manifest,
        None,
    )

    assert any(
        e.code == ErrorCode.STUB_FUNCTION_DETECTED
        and e.severity == Severity.WARNING
        and e.location is not None
        and e.location.file == "src/greet.py"
        for e in errors
    )


def test_validate_file_spec_preserves_required_import_error(project: Path) -> None:
    manifest_path = _write_manifest(
        project,
        """schema: "2"
goal: "Add service"
files:
  create:
    - path: src/service.py
      imports:
        - src/models/user.py
      artifacts:
        - kind: function
          name: load_user
validate:
  - pytest tests/ -v
""",
    )
    _write_source(project, "src/service.py", "def load_user():\n    return None\n")
    manifest = load_manifest(manifest_path)
    fs = manifest.file_spec_for("src/service.py")
    assert fs is not None

    errors = _validator(project).validate_file_spec(fs, manifest, None)

    assert any(
        e.code == ErrorCode.MISSING_REQUIRED_IMPORT
        and e.message == "Required import 'src/models/user.py' not found in src/service.py"
        and e.suggestion == "Add an import for 'src/models/user.py'"
        for e in errors
    )


def test_compare_artifacts_preserves_strict_mode_extra_public_artifact_error() -> None:
    errors = compare_artifacts(
        expected=[ArtifactSpec(kind=ArtifactKind.FUNCTION, name="declared")],
        found=[
            FoundArtifact(kind=ArtifactKind.FUNCTION, name="declared", line=1),
            FoundArtifact(kind=ArtifactKind.FUNCTION, name="extra", line=4),
        ],
        file_path="src/service.py",
        is_strict=True,
    )

    assert [
        (e.code, e.message, e.location.line if e.location else None) for e in errors
    ] == [
        (
            ErrorCode.UNEXPECTED_ARTIFACT,
            "Unexpected public artifact 'extra' in src/service.py",
            4,
        )
    ]
