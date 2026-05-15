"""Behavioral tests for removed_artifacts manifest field and E311 validator."""

from __future__ import annotations

from pathlib import Path


from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.types import (
    ArtifactKind,
    Manifest,
    RemovedArtifactSpec,
)
from maid_runner.core.validate import ValidationEngine


class TestRemovedArtifactSpecFields:
    def test_carries_identity_fields(self) -> None:
        spec = RemovedArtifactSpec(
            kind=ArtifactKind.METHOD,
            name="old_method",
            file="src/greet.py",
            of="Greeter",
            reason="deprecated",
        )
        assert spec.kind == ArtifactKind.METHOD
        assert spec.name == "old_method"
        assert spec.file == "src/greet.py"
        assert spec.of == "Greeter"
        assert spec.reason == "deprecated"

    def test_of_field_optional_for_function(self) -> None:
        spec = RemovedArtifactSpec(
            kind=ArtifactKind.FUNCTION,
            name="old_func",
            file="src/x.py",
            reason="removed",
        )
        assert spec.of is None


class TestManifestRemovedArtifactsField:
    def test_parses_removed_artifacts_from_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "m.manifest.yaml"
        path.write_text(
            """schema: "2"
goal: "x"
type: feature
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
  - pytest
"""
        )
        manifest: Manifest = load_manifest(path)
        assert len(manifest.removed_artifacts) == 1
        entry = manifest.removed_artifacts[0]
        assert entry.name == "old_method"
        assert entry.of == "Greeter"
        assert entry.file == "src/greet.py"
        assert entry.reason == "deprecated"

    def test_defaults_to_empty_tuple_when_absent(self, tmp_path: Path) -> None:
        path = tmp_path / "m.manifest.yaml"
        path.write_text(
            """schema: "2"
goal: "x"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
"""
        )
        manifest = load_manifest(path)
        assert manifest.removed_artifacts == ()


class TestValidateRemovedArtifactsClean:
    def test_no_error_when_removed_artifact_truly_absent(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "greet.py").write_text(
            "class Greeter:\n    def new_method(self) -> None:\n        pass\n"
        )
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
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
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert errors == []


class TestValidateRemovedArtifactsViolation:
    def test_error_when_removed_method_still_present(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "greet.py").write_text(
            "class Greeter:\n"
            "    def old_method(self) -> None:\n        pass\n"
            "    def new_method(self) -> None:\n        pass\n"
        )
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
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
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
        assert errors[0].severity == Severity.ERROR

    def test_error_when_removed_function_still_present(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "utils.py").write_text(
            "def old_func() -> None:\n    pass\n\n\ndef new_func() -> None:\n    pass\n"
        )
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: function
    name: old_func
    file: src/utils.py
    reason: "deprecated"
files:
  edit:
    - path: src/utils.py
      artifacts:
        - kind: function
          name: new_func
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT


class TestValidateRemovedArtifactsUnverifiable:
    def test_error_when_removed_artifact_file_missing(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: function
    name: ghost
    file: src/does_not_exist.py
    reason: "bypass attempt"
files:
  create:
    - path: src/other.py
      artifacts:
        - kind: function
          name: real_func
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
        assert errors[0].severity == Severity.ERROR

    def test_error_when_removed_artifact_file_is_unparsable(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "broken.py").write_text("def foo(:\n    return\n")
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: function
    name: foo
    file: src/broken.py
    reason: "bypass attempt via broken syntax"
files:
  create:
    - path: src/other.py
      artifacts:
        - kind: function
          name: real_func
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
        assert errors[0].severity == Severity.ERROR

    def test_error_when_removed_artifact_file_has_no_validator(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "notes.txt").write_text("not a python file")
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: function
    name: ghost
    file: src/notes.txt
    reason: "bypass attempt"
files:
  create:
    - path: src/other.py
      artifacts:
        - kind: function
          name: real_func
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
        assert errors[0].severity == Severity.ERROR


class TestValidateRemovedArtifactsEmpty:
    def test_no_errors_when_manifest_has_no_removed_artifacts(
        self, tmp_path: Path
    ) -> None:
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert errors == []


class TestValidateRemovedArtifactsOwnership:
    def test_error_when_method_removal_lacks_owner(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "greet.py").write_text(
            "class Greeter:\n    def old_method(self) -> None:\n        pass\n"
        )
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: method
    name: old_method
    file: src/greet.py
    reason: "claimed removed but ownerless"
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: class
          name: Greeter
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
        assert errors[0].severity == Severity.ERROR

    def test_error_when_attribute_removal_lacks_owner(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "greet.py").write_text("class Greeter:\n    name: str = 'hi'\n")
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: attribute
    name: name
    file: src/greet.py
    reason: "ownerless attribute claim"
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: class
          name: Greeter
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=tmp_path)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT


class TestValidateRemovedArtifactsPathContainment:
    def test_error_when_removed_artifact_path_escapes_project_root(
        self, tmp_path: Path
    ) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        (tmp_path / "escaped.py").write_text("def other() -> None:\n    return\n")
        manifest_path = project_root / "m.manifest.yaml"
        manifest_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: function
    name: foo
    file: ../escaped.py
    reason: "bypass attempt"
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: real_func
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=project_root)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT
        assert errors[0].severity == Severity.ERROR

    def test_error_when_removed_artifact_path_is_absolute(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        outside = tmp_path / "escaped.py"
        outside.write_text("def other() -> None:\n    return\n")
        manifest_path = project_root / "m.manifest.yaml"
        manifest_path.write_text(
            f"""schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: function
    name: foo
    file: {outside}
    reason: "bypass attempt"
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: real_func
validate:
  - pytest
"""
        )
        manifest = load_manifest(manifest_path)
        engine = ValidationEngine(project_root=project_root)
        errors = engine.validate_removed_artifacts(manifest)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT


class TestSaveManifestRoundTripsRemovedArtifacts:
    def test_save_then_load_preserves_removed_artifacts(self, tmp_path: Path) -> None:
        from maid_runner.core.manifest import load_manifest, save_manifest

        original_path = tmp_path / "m.manifest.yaml"
        original_path.write_text(
            """schema: "2"
goal: "x"
type: feature
removed_artifacts:
  - kind: method
    name: old_method
    of: Greeter
    file: src/greet.py
    reason: "deprecated v1 API"
  - kind: function
    name: helper
    file: src/util.py
    reason: "inlined elsewhere"
files:
  edit:
    - path: src/greet.py
      artifacts:
        - kind: method
          name: new_method
          of: Greeter
validate:
  - pytest
"""
        )
        manifest = load_manifest(original_path)
        assert len(manifest.removed_artifacts) == 2

        out_path = tmp_path / "m-saved.manifest.yaml"
        save_manifest(manifest, out_path)

        reloaded = load_manifest(out_path)
        assert len(reloaded.removed_artifacts) == 2
        by_name = {ra.name: ra for ra in reloaded.removed_artifacts}
        assert by_name["old_method"].of == "Greeter"
        assert by_name["old_method"].file == "src/greet.py"
        assert by_name["old_method"].reason == "deprecated v1 API"
        assert by_name["helper"].of is None
        assert by_name["helper"].file == "src/util.py"
        assert by_name["helper"].reason == "inlined elsewhere"


class TestErrorCodeRemovedArtifactStillPresent:
    def test_code_is_E311_or_similar(self) -> None:
        assert ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT.value.startswith("E")
