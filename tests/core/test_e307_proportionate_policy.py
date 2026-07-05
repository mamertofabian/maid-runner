from __future__ import annotations

import json
from pathlib import Path

from maid_runner.cli.commands._format import format_verify_result, format_verify_summary
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def _finding(
    path: str,
    *,
    severity: Severity,
    message: str | None = None,
) -> ValidationError:
    return ValidationError(
        code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
        message=message or f"No validator available for '{path}'",
        severity=severity,
        location=Location(file=path),
    )


def _validation(
    slug: str,
    *,
    warnings: list[ValidationError],
    success: bool = True,
) -> ValidationResult:
    return ValidationResult(
        success=success,
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        warnings=warnings,
    )


def _verification_result(warnings: list[ValidationError]) -> VerificationResult:
    return VerificationResult(
        stages=(
            VerificationStageResult(
                name="implementation",
                success=True,
                _validation=BatchValidationResult(
                    results=[_validation("docs", warnings=warnings)],
                    total_manifests=1,
                    passed=1,
                    failed=0,
                    skipped=0,
                ),
            ),
        )
    )


def test_no_validator_severity_downgrades_recognized_non_code_extensions() -> None:
    from maid_runner.core.diagnostic_policy import no_validator_severity

    paths = [
        "README.md",
        "docs/guide.markdown",
        "docs/notes.rst",
        "docs/plain.txt",
        "pyproject.toml",
        "package-lock.json",
        "tsconfig.jsonc",
        "config/settings.yaml",
        "config/settings.yml",
        "setup.cfg",
        "tox.ini",
        "uv.lock",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".env.example",
    ]

    assert [no_validator_severity(path) for path in paths] == [
        Severity.INFO for _path in paths
    ]


def test_no_validator_severity_keeps_warning_for_source_like_extensions() -> None:
    from maid_runner.core.diagnostic_policy import no_validator_severity

    assert no_validator_severity("cmd/server.go") == Severity.WARNING
    assert no_validator_severity("frontend/postcss.config.cjs") == Severity.WARNING
    assert no_validator_severity("scripts/build.mjs") == Severity.WARNING
    assert no_validator_severity("lib/task.rb") == Severity.WARNING


def test_validation_emits_info_e307_for_declared_non_code_file(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Project\n")
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "docs.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Track docs"
type: snapshot
files:
  edit:
    - path: README.md
      artifacts:
        - kind: function
          name: placeholder
validate:
  - uv run python -m pytest tests/core/test_e307_proportionate_policy.py -v
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        load_manifest(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        include_chain_diagnostics=False,
        include_plugin_diagnostics=False,
    )

    assert result.success is True
    assert [
        (
            warning.code,
            warning.severity,
            warning.location.file if warning.location else "",
        )
        for warning in result.warnings
    ] == [(ErrorCode.VALIDATOR_NOT_AVAILABLE, Severity.INFO, "README.md")]


def test_build_summary_aggregates_info_diagnostics_by_code() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    info_findings = [
        _finding("README.md", severity=Severity.INFO),
        _finding("pyproject.toml", severity=Severity.INFO),
        _finding("docs/guide.md", severity=Severity.INFO),
    ]
    source_warning = _finding("cmd/server.go", severity=Severity.WARNING)

    summary = build_verify_summary(
        _verification_result([*info_findings, source_warning])
    )

    assert summary.raw_info_count == 3
    assert [
        (group.code, group.location, group.count) for group in summary.info_groups
    ] == [("E307", None, 3)]
    assert summary.raw_warning_count == 1
    assert [
        (group.code, group.location, group.count) for group in summary.warning_groups
    ] == [("E307", "cmd/server.go", 1)]


def test_summary_renders_single_proportionate_info_line() -> None:
    result = _verification_result(
        [
            _finding("README.md", severity=Severity.INFO),
            _finding("pyproject.toml", severity=Severity.INFO),
            _finding("docs/guide.md", severity=Severity.INFO),
            _finding("cmd/server.go", severity=Severity.WARNING),
        ]
    )

    output = format_verify_summary(result)

    assert "1 warnings unique / 1 raw" in output
    assert "INFO (deduplicated 3 -> 1):" in output
    assert (
        output.count(
            "INFO E307 x3 no validator available for 3 declared non-code files"
        )
        == 1
    )
    assert "README.md" not in output
    assert "pyproject.toml" not in output
    assert "cmd/server.go" in output


def test_per_file_info_records_survive_in_json_outputs() -> None:
    result = _verification_result(
        [
            _finding("README.md", severity=Severity.INFO),
            _finding("pyproject.toml", severity=Severity.INFO),
        ]
    )

    full_payload = json.loads(format_verify_result(result, json_mode=True))
    summary_payload = json.loads(format_verify_summary(result, json_mode=True))

    records = full_payload["stages"][0]["details"]["results"][0]["warnings"]
    assert [
        (record["code"], record["severity"], record["location"]["file"])
        for record in records
    ] == [
        ("E307", "info", "README.md"),
        ("E307", "info", "pyproject.toml"),
    ]
    assert summary_payload["findings"]["info"] == [
        {
            "code": "E307",
            "message": "no validator available for 2 declared non-code files",
            "location": None,
            "count": 2,
        }
    ]


def test_info_diagnostics_do_not_block_verify_warning_policy(tmp_path: Path) -> None:
    from maid_runner.cli.commands.verify import _warnings_are_blocking
    from maid_runner.core.verify_summary import build_verify_summary

    manifest_path = tmp_path / "manifests" / "strict.manifest.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """schema: "2"
goal: "Strict warning policy"
type: fix
created: "2026-07-03T00:00:00Z"
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: app
validate:
  - uv run python -m pytest tests/core/test_e307_proportionate_policy.py -v
"""
    )
    info = ValidationError(
        code=ErrorCode.MISSING_ASSERTIONS,
        message="Informational diagnostic carried in warnings collection",
        severity=Severity.INFO,
        location=Location(file="tests/test_app.py"),
    )

    summary = build_verify_summary(_verification_result([info]))

    assert summary.raw_info_count == 1
    assert _warnings_are_blocking([info], str(manifest_path), tmp_path) is False
