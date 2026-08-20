"""Behavioral contract for unioning chain-level artifact coverage reports."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import main
from maid_runner.core import artifact_coverage
from maid_runner.core.artifact_coverage import (
    ArtifactCoverageExecutionSummary,
    ArtifactCoverageFinding,
    ArtifactCoverageReport,
)
from maid_runner.core.result import ErrorCode, Location, ValidationError


def test_merge_unions_execution_by_complete_identity_and_regenerates_e710() -> None:
    alpha_red = _finding("src/a.py", "alpha", executed=False)
    alpha_green = _finding("src/a.py", "alpha", executed=True)
    beta_green = _finding("src/a.py", "beta", executed=True)
    beta_red = _finding("src/a.py", "beta", executed=False)
    method_red = _finding("src/a.py", "run", parent="Service", executed=False)
    kind_collision_red = _finding("src/a.py", "alpha", kind="class", executed=False)
    other_file_green = _finding("src/b.py", "alpha", executed=True)

    result = artifact_coverage.merge_artifact_coverage_reports(
        (
            _report(
                alpha_red,
                beta_green,
                method_red,
                kind_collision_red,
                errors=(
                    _associated_noncanonical_e710(alpha_red),
                    _associated_noncanonical_e710(method_red),
                    _associated_noncanonical_e710(kind_collision_red),
                ),
            ),
            _report(
                alpha_green,
                beta_red,
                other_file_green,
                errors=(_associated_noncanonical_e710(beta_red),),
            ),
        )
    )

    assert result.findings == (
        alpha_green,
        beta_green,
        method_red,
        kind_collision_red,
        other_file_green,
    )
    assert result.errors == (
        _canonical_e710(method_red),
        _canonical_e710(kind_collision_red),
    )


def test_merge_preserves_noncoverage_and_malformed_e710_diagnostics() -> None:
    alpha = _finding("src/a.py", "alpha", executed=False)
    beta = _finding("src/a.py", "beta", executed=False)
    gamma = _finding("src/b.py", "gamma", executed=False)
    first_malformed = _noncanonical_e710("first malformed")
    second_malformed = _noncanonical_e710("second malformed")
    orphan = _noncanonical_e710("orphan")
    command_error = ValidationError(
        code=ErrorCode.FILE_READ_ERROR,
        message="coverage command failed",
    )

    result = artifact_coverage.merge_artifact_coverage_reports(
        (
            _report(alpha, beta, errors=(first_malformed, command_error)),
            _report(gamma, errors=(second_malformed, orphan)),
        )
    )

    assert result.errors == (
        first_malformed,
        command_error,
        second_malformed,
        orphan,
        _canonical_e710(alpha),
        _canonical_e710(beta),
        _canonical_e710(gamma),
    )


def test_merge_preserves_equal_count_orphaned_e710_diagnostic() -> None:
    alpha_red = _finding("src/a.py", "alpha", executed=False)
    alpha_green = _finding("src/a.py", "alpha", executed=True)
    orphan = ValidationError(
        code=ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        message="Artifact 'beta' was not exercised",
        location=Location(file="src/b.py"),
        suggestion="orphaned diagnostic",
    )

    result = artifact_coverage.merge_artifact_coverage_reports(
        (
            _report(alpha_red, errors=(orphan,)),
            _report(alpha_green),
        )
    )

    assert result.findings == (alpha_green,)
    assert result.errors == (orphan,)


def test_merge_retains_first_execution_summary_without_claiming_mixed_provenance() -> (
    None
):
    summary = ArtifactCoverageExecutionSummary(
        command_count=2,
        isolated_count=1,
        serial_count=1,
        lane_count=1,
    )
    later_summary = ArtifactCoverageExecutionSummary(
        command_count=9,
        isolated_count=9,
        serial_count=0,
        lane_count=3,
    )

    result = artifact_coverage.merge_artifact_coverage_reports(
        (
            ArtifactCoverageReport((), (), provenance="exact", cache_hit=True),
            ArtifactCoverageReport((), (), execution=summary, provenance="derived"),
            ArtifactCoverageReport((), (), execution=later_summary),
        )
    )

    assert result.execution is summary
    assert result.provenance is None
    assert result.cache_hit is False


def test_directory_validation_accepts_execution_from_either_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_duplicate_owner_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["validate", "--artifact-coverage", "--quiet"]) == 0


def test_verify_artifact_coverage_accepts_execution_from_either_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_duplicate_owner_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert (
        main(
            [
                "verify",
                "--artifact-coverage",
                "--no-changed-scope",
                "--summary",
            ]
        )
        == 0
    )


def _finding(
    file_path: str,
    name: str,
    *,
    parent: str | None = None,
    kind: str | None = None,
    executed: bool,
) -> ArtifactCoverageFinding:
    return ArtifactCoverageFinding(
        artifact_name=name,
        artifact_kind=kind or ("method" if parent else "function"),
        parent_class=parent,
        file_path=file_path,
        executed=executed,
    )


def _report(
    *findings: ArtifactCoverageFinding,
    errors: tuple[ValidationError, ...] = (),
) -> ArtifactCoverageReport:
    return ArtifactCoverageReport(findings=findings, errors=errors)


def _noncanonical_e710(message: str = "noncanonical") -> ValidationError:
    return ValidationError(
        code=ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        message=message,
        location=Location(file="wrong.py"),
        suggestion="wrong suggestion",
    )


def _associated_noncanonical_e710(
    finding: ArtifactCoverageFinding,
) -> ValidationError:
    display_name = (
        f"{finding.parent_class}.{finding.artifact_name}"
        if finding.parent_class
        else finding.artifact_name
    )
    return ValidationError(
        code=ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        message=f"Artifact '{display_name}' was not exercised",
        location=Location(file=finding.file_path),
        suggestion="noncanonical suggestion",
    )


def _canonical_e710(finding: ArtifactCoverageFinding) -> ValidationError:
    display_name = (
        f"{finding.parent_class}.{finding.artifact_name}"
        if finding.parent_class
        else finding.artifact_name
    )
    return ValidationError(
        code=ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        message=(
            f"No body line of declared artifact '{display_name}' was executed by tests"
        ),
        location=Location(file=finding.file_path),
        suggestion=(
            "Strengthen the behavioral test so it executes the declared artifact body."
        ),
    )


def _write_duplicate_owner_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "target.py").write_text(
        "def target(value: str) -> str:\n    return value.strip().upper()\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_exec.py").write_text(
        "from src.target import target\n\ndef test_exec():\n    assert target(' executed ') == 'EXECUTED'\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_noop.py").write_text(
        "from src.target import target\n\ndef test_noop():\n    assert callable(target)\n",
        encoding="utf-8",
    )
    for slug, test_file, created in (
        ("owner-a", "tests/test_exec.py", "2026-08-17T08:00:00Z"),
        ("owner-b", "tests/test_noop.py", "2026-08-17T08:00:01Z"),
    ):
        payload = {
            "schema": "2",
            "goal": f"Contract target through {slug}",
            "type": "fix",
            "created": created,
            "files": {
                "edit": [
                    {
                        "path": "src/target.py",
                        "artifacts": [
                            {
                                "kind": "function",
                                "name": "target",
                                "args": [{"name": "value", "type": "str"}],
                                "returns": "str",
                            }
                        ],
                    }
                ],
                "read": [test_file],
            },
            "validate": [f"python -m pytest -q {test_file}"],
        }
        (root / "manifests" / f"{slug}.manifest.yaml").write_text(
            yaml.safe_dump(payload, sort_keys=False),
            encoding="utf-8",
        )
