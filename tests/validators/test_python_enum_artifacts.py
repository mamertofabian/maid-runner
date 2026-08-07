"""Behavioral contract for first-class Python enum artifacts."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core._implementation_validation import compare_artifacts
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.supersession_audit import SupersessionAuditor
from maid_runner.core.types import ArtifactKind, ArtifactSpec, ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.python import PythonValidator


def test_python_stdlib_enum_subclasses_expose_canonical_enum_identity() -> None:
    source = """from enum import Enum
from enum import IntEnum as NumberEnum
import enum
import enum as enum_types

class DirectStatus(str, Enum):
    READY = "ready"

class NumericStatus(NumberEnum):
    READY = 1

class FlagStatus(enum.Flag):
    READY = enum.auto()

class AliasedFlagStatus(enum_types.IntFlag):
    READY = enum_types.auto()
"""

    result = PythonValidator().collect_implementation_artifacts(source, "src/status.py")

    for name in ("DirectStatus", "NumericStatus", "FlagStatus", "AliasedFlagStatus"):
        artifact = next(
            item for item in result.artifacts if item.name == name and item.of is None
        )
        assert artifact.kind == ArtifactKind.CLASS
        assert artifact._canonical_kind == ArtifactKind.ENUM
        assert any(
            item.of == name and item.name == "READY" for item in result.artifacts
        )


def test_non_stdlib_enum_named_bases_remain_ordinary_classes() -> None:
    source = """class Enum:
    LOCAL = "local"

class LocalStatus(Enum):
    READY = "ready"

from another_package import Enum as OtherEnum

class ImportedStatus(OtherEnum):
    READY = "ready"
"""

    result = PythonValidator().collect_implementation_artifacts(source, "src/status.py")

    for name in ("Enum", "LocalStatus", "ImportedStatus"):
        artifact = next(item for item in result.artifacts if item.name == name)
        assert artifact.kind == ArtifactKind.CLASS
        assert artifact._canonical_kind is None
    assert any(
        artifact.kind == ArtifactKind.ATTRIBUTE
        and artifact.name == "READY"
        and artifact.of == "LocalStatus"
        for artifact in result.artifacts
    )
    assert any(
        artifact.kind == ArtifactKind.ATTRIBUTE
        and artifact.name == "READY"
        and artifact.of == "ImportedStatus"
        for artifact in result.artifacts
    )


def test_canonical_enum_projection_is_contract_sensitive() -> None:
    found = [
        FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Status",
            bases=("Enum",),
            line=3,
            _canonical_kind=ArtifactKind.ENUM,
        ),
        FoundArtifact(
            kind=ArtifactKind.ATTRIBUTE,
            name="READY",
            of="Status",
            line=4,
        ),
    ]

    enum_errors = compare_artifacts(
        expected=[ArtifactSpec(kind=ArtifactKind.ENUM, name="Status")],
        found=found,
        file_path="src/status.py",
        is_strict=True,
    )
    legacy_errors = compare_artifacts(
        expected=[
            ArtifactSpec(
                kind=ArtifactKind.CLASS,
                name="Status",
                bases=("Enum",),
            ),
            ArtifactSpec(
                kind=ArtifactKind.ATTRIBUTE,
                name="READY",
                of="Status",
            ),
        ],
        found=found,
        file_path="src/status.py",
        is_strict=True,
    )

    assert enum_errors == []
    assert legacy_errors == []


def test_enum_projection_rejects_later_same_name_rebindings() -> None:
    sources = (
        """from enum import Enum
class Status(Enum):
    READY = 1
class Status:
    OTHER = 2
""",
        """from enum import Enum
class Status(Enum):
    READY = 1
Status = object()
""",
    )

    for source in sources:
        found = PythonValidator().collect_implementation_artifacts(
            source, "src/status.py"
        )
        errors = compare_artifacts(
            expected=[ArtifactSpec(kind=ArtifactKind.ENUM, name="Status")],
            found=found.artifacts,
            file_path="src/status.py",
            is_strict=True,
        )

        assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in errors)
        assert any(error.code == ErrorCode.UNEXPECTED_ARTIFACT for error in errors)


def test_enum_detection_rejects_non_top_level_and_shadowed_bindings() -> None:
    sources = (
        """if enabled:
    from enum import Enum
class Status(Enum):
    READY = 1
""",
        """from enum import Enum
for Enum in local_bases:
    pass
class Status(Enum):
    READY = 1
""",
        """from enum import Enum
from local_bases import *
class Status(Enum):
    READY = 1
""",
        """from enum import Enum
match LocalBase:
    case Enum:
        pass
class Status(Enum):
    READY = 1
""",
        """from enum import Enum
class LocalBase:
    pass
@(Enum := LocalBase)
class Marker:
    pass
class Status(Enum):
    READY = 1
""",
        """from enum import Enum
class LocalBase:
    pass
def marker(value=(Enum := LocalBase)):
    return value
class Status(Enum):
    READY = 1
""",
    )

    for source in sources:
        result = PythonValidator().collect_implementation_artifacts(
            source, "src/status.py"
        )
        status = next(
            artifact
            for artifact in result.artifacts
            if artifact.name == "Status" and artifact.of is None
        )

        assert status.kind == ArtifactKind.CLASS
        assert status._canonical_kind is None


def test_python_enum_manifest_validates_direct_and_module_qualified_member_usage(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    manifest_path = tmp_path / "manifests" / "endpoint-status.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Add endpoint probe status"
type: feature
created: "2026-08-05T00:00:00Z"
files:
  create:
    - path: src/status.py
      artifacts:
        - kind: enum
          name: EndpointProbeStatus
  read:
    - tests/test_status.py
validate:
  - pytest tests/test_status.py
""",
        encoding="utf-8",
    )
    (tmp_path / "src" / "status.py").write_text(
        """from enum import Enum

class EndpointProbeStatus(str, Enum):
    COMPATIBLE_OWNED = "compatible_owned"
    COMPATIBLE_FOREIGN = "compatible_foreign"
""",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_status.py").write_text(
        """from src.status import EndpointProbeStatus
import src.status as status_module

def test_direct_member_access() -> None:
    assert EndpointProbeStatus.COMPATIBLE_OWNED.value == "compatible_owned"

def test_module_qualified_member_access() -> None:
    assert status_module.EndpointProbeStatus.COMPATIBLE_FOREIGN.value == "compatible_foreign"
""",
        encoding="utf-8",
    )

    engine = ValidationEngine(project_root=tmp_path)
    implementation = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
    behavioral = engine.validate(manifest_path, mode=ValidationMode.BEHAVIORAL)

    assert implementation.success is True
    assert behavioral.success is True
    assert not any(
        error.code
        in {
            ErrorCode.ARTIFACT_NOT_DEFINED,
            ErrorCode.UNEXPECTED_ARTIFACT,
            ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
        }
        for error in implementation.errors + behavioral.errors
    )


def test_legacy_python_enum_class_and_member_manifest_remains_valid(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    manifest_path = tmp_path / "manifests" / "legacy-status.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Preserve legacy enum snapshot"
type: system-snapshot
created: "2026-08-05T00:00:00Z"
files:
  snapshot:
    - path: src/status.py
      artifacts:
        - kind: class
          name: LegacyStatus
          bases: [Enum]
        - kind: attribute
          name: READY
          of: LegacyStatus
validate:
  - pytest tests/ -v
""",
        encoding="utf-8",
    )
    (tmp_path / "src" / "status.py").write_text(
        """from enum import Enum

class LegacyStatus(Enum):
    READY = "ready"
""",
        encoding="utf-8",
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    assert result.success is True
    assert not any(
        error.code in {ErrorCode.ARTIFACT_NOT_DEFINED, ErrorCode.UNEXPECTED_ARTIFACT}
        for error in result.errors
    )


def test_removed_python_enum_still_present_reports_e311(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "status.py").write_text(
        """from enum import Enum

class Status(Enum):
    READY = "ready"
""",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "remove-status.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Remove status"
type: refactor
removed_artifacts:
  - kind: enum
    name: Status
    file: src/status.py
    reason: "retired"
files:
  scope:
    - path: src/status.py
      reason: "verify the removal claim"
validate:
  - pytest tests/ -v
""",
        encoding="utf-8",
    )

    errors = ValidationEngine(project_root=tmp_path).validate_removed_artifacts(
        load_manifest(manifest_path)
    )

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT


def test_python_enum_removed_artifact_does_not_bypass_supersession_audit(
    tmp_path: Path,
) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "status.py").write_text(
        """from enum import Enum

class Status(Enum):
    READY = "ready"
""",
        encoding="utf-8",
    )
    (manifests_dir / "old.manifest.yaml").write_text(
        """schema: "2"
goal: "Add status"
type: feature
created: "2026-08-01T00:00:00Z"
files:
  create:
    - path: src/status.py
      artifacts:
        - kind: enum
          name: Status
validate:
  - pytest tests/ -v
""",
        encoding="utf-8",
    )
    (manifests_dir / "new.manifest.yaml").write_text(
        """schema: "2"
goal: "Replace status"
type: refactor
created: "2026-08-02T00:00:00Z"
supersedes: [old]
removed_artifacts:
  - kind: enum
    name: Status
    file: src/status.py
    reason: "claimed retired"
files:
  create:
    - path: src/replacement.py
      artifacts:
        - kind: function
          name: replacement
validate:
  - pytest tests/ -v
""",
        encoding="utf-8",
    )

    chain = ManifestChain(manifests_dir, project_root=tmp_path)
    violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)

    assert len(violations) == 1
    assert violations[0].artifact_name == "Status"
