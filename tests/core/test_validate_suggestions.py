"""Behavioral tests for generated draft validate-command suggestions."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.diff_scope import DiffScopeResult, FileArtifactDelta
from maid_runner.core.manifest_from_diff import build_from_diff_manifest
from maid_runner.core.types import ArtifactKind, ArtifactSpec
from maid_runner.core.validate_suggestions import suggest_validate_commands
from maid_runner.validators.base import BaseValidator, CollectionResult
from maid_runner.validators.registry import ValidatorRegistry


def _write(project_dir: Path, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _artifact(
    name: str,
    *,
    kind: ArtifactKind = ArtifactKind.FUNCTION,
    of: str | None = None,
) -> ArtifactSpec:
    return ArtifactSpec(kind=kind, name=name, of=of)


def _diff(*deltas: FileArtifactDelta) -> DiffScopeResult:
    return DiffScopeResult(
        created=tuple(delta.path for delta in deltas),
        edited=(),
        deleted=(),
        deltas=deltas,
    )


def test_existing_test_file_referencing_changed_artifact_is_suggested(tmp_path):
    _write(
        tmp_path,
        "tests/test_service.py",
        "from app.service import build\n\n\ndef test_build():\n    assert build() == 1\n",
    )
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("build"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "pytest tests/test_service.py -v",
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_existing_test_file_without_changed_artifact_reference_is_excluded(tmp_path):
    _write(
        tmp_path,
        "tests/test_unrelated.py",
        "from app.other import other\n\n\ndef test_other():\n    assert other() == 1\n",
    )
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("build"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_missing_referenced_looking_path_is_not_suggested(tmp_path):
    _write(
        tmp_path, "tests/test_unrelated.py", "def test_unrelated():\n    assert True\n"
    )
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("missing_test"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert "pytest tests/test_missing_test.py -v" not in commands
    assert commands == (
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_no_evidence_yields_only_schema_validate_command(tmp_path):
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("build"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_suggestions_are_sorted_and_deduplicated(tmp_path):
    _write(
        tmp_path,
        "tests/test_zeta.py",
        "from app.service import build\n\n\ndef test_zeta():\n    assert build() == 1\n",
    )
    _write(
        tmp_path,
        "tests/test_alpha.py",
        "from app.service import build\n\n\ndef test_alpha():\n    assert build() == 1\n",
    )
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("build"),),
            signature_changed=(_artifact("build"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "pytest tests/test_alpha.py -v",
        "pytest tests/test_zeta.py -v",
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_class_member_artifact_requires_matching_parent(tmp_path):
    _write(
        tmp_path,
        "tests/test_service.py",
        "from app.service import OtherService\n\n\ndef test_run():\n    service = OtherService()\n    assert service.run() == 1\n",
    )
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("run", kind=ArtifactKind.METHOD, of="Service"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_unparseable_test_files_are_skipped(tmp_path):
    _write(tmp_path, "tests/test_broken.py", "def test_broken(:\n")
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("test_broken"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_unavailable_optional_validator_test_files_are_skipped(tmp_path, monkeypatch):
    class MissingOptionalValidator(BaseValidator):
        def __init__(self) -> None:
            raise ImportError("optional parser unavailable")

        @classmethod
        def supported_extensions(cls) -> tuple[str, ...]:
            return (".ts",)

        def collect_implementation_artifacts(self, source, file_path):
            return CollectionResult([], "typescript", str(file_path))

        def collect_behavioral_artifacts(self, source, file_path):
            return CollectionResult([], "typescript", str(file_path))

    registry = ValidatorRegistry()
    registry.register(MissingOptionalValidator)
    monkeypatch.setattr(
        ValidatorRegistry,
        "with_builtin_validators",
        classmethod(lambda cls: registry),
    )
    _write(
        tmp_path,
        "tests/service.test.ts",
        "import { build } from '../src/service';\n"
        "test('build', () => expect(build()).toBe(1));\n",
    )
    diff = _diff(
        FileArtifactDelta(
            path="src/service.ts",
            added=(_artifact("build"),),
        )
    )

    commands = suggest_validate_commands(
        diff,
        tmp_path,
        "manifests/drafts/demo.manifest.yaml",
    )

    assert commands == (
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    )


def test_from_diff_rendering_includes_validate_suggestions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path,
        "tests/test_service.py",
        "from app.service import build\n\n\ndef test_build():\n    assert build() == 1\n",
    )
    diff = _diff(
        FileArtifactDelta(
            path="app/service.py",
            added=(_artifact("build"),),
        )
    )

    data = build_from_diff_manifest(diff, tmp_path, "demo")

    assert data["validate"] == [
        "pytest tests/test_service.py -v",
        "maid validate manifests/drafts/demo.manifest.yaml --mode schema --quiet",
    ]
    assert data["metadata"]["needs_review"] is True
