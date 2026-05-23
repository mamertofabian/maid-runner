"""Focused characterization tests for behavioral coverage validation."""

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


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


def coverage_errors(result):
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
    ]


def test_public_artifact_without_test_file_reports_no_test_files(project):
    manifest_path = write_manifest(
        project,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
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
    write_source(project, "src/widget.py", "def render():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is False
    assert any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)


def test_snapshot_manifest_without_test_file_does_not_report_no_test_files(project):
    manifest_path = write_manifest(
        project,
        "snapshot-utils.manifest.yaml",
        """schema: "2"
goal: "Snapshot utils"
type: snapshot
files:
  create:
    - path: src/utils.py
      artifacts:
        - kind: function
          name: helper
validate:
  - make check
""",
    )
    write_source(project, "src/utils.py", "def helper():\n    pass\n")

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert not any(error.code == ErrorCode.NO_TEST_FILES for error in result.errors)


def test_unreferenced_public_artifact_reports_e200_error(project):
    manifest_path = write_manifest(
        project,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
    )
    write_source(
        project,
        "src/widget.py",
        "def render():\n    pass\n\ndef update():\n    pass\n",
    )
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import render\n\n"
        "def test_render():\n"
        "    render()\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False
    assert len(untested) == 1
    assert "update" in untested[0].message
    assert untested[0].severity.value == "error"


def test_import_only_reference_is_not_behavioral_coverage(project):
    manifest_path = write_manifest(
        project,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
    )
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import update\n\n"
        "def test_widget_placeholder():\n"
        "    assert True\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False
    assert len(untested) == 1
    assert "update" in untested[0].message


def test_local_same_name_helper_without_identity_does_not_cover_artifact(project):
    manifest_path = write_manifest(
        project,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
    )
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    write_source(
        project,
        "tests/test_widget.py",
        "def update():\n"
        "    return 'local'\n\n"
        "def test_widget_local_update():\n"
        "    assert update() == 'local'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    untested = coverage_errors(result)

    assert result.success is False
    assert len(untested) == 1
    assert "update" in untested[0].message


def test_imported_production_call_satisfies_behavioral_coverage(project):
    manifest_path = write_manifest(
        project,
        "add-widget.manifest.yaml",
        """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
    )
    write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
    write_source(
        project,
        "tests/test_widget.py",
        "from src.widget import update\n\n"
        "def test_widget_update():\n"
        "    assert update() == 'updated'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert coverage_errors(result) == []


def test_snapshot_manifest_is_exempt_from_behavioral_coverage(project):
    manifest_path = write_manifest(
        project,
        "snapshot-utils.manifest.yaml",
        """schema: "2"
goal: "Snapshot utils"
type: snapshot
files:
  create:
    - path: src/utils.py
      artifacts:
        - kind: function
          name: helper
  read:
    - tests/test_utils.py
validate:
  - pytest tests/test_utils.py -v
""",
    )
    write_source(project, "src/utils.py", "def helper():\n    pass\n")
    write_source(project, "tests/test_utils.py", "def test_smoke():\n    assert True\n")

    engine = ValidationEngine(project_root=project)
    implementation = engine.validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )
    behavioral = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert implementation.success is True
    assert behavioral.success is True
    assert coverage_errors(implementation) == []
    assert coverage_errors(behavioral) == []
