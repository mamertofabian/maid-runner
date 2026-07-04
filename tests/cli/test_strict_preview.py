from __future__ import annotations

import argparse
import json
from pathlib import Path


def test_parser_accepts_strict_preview_for_validate_and_verify() -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.validate import cmd_validate
    from maid_runner.cli.commands.verify import cmd_verify

    parser = build_parser()

    validate_args = parser.parse_args(["validate", "--strict-preview"])
    verify_args = parser.parse_args(["verify", "--strict-preview"])

    assert callable(cmd_validate)
    assert callable(cmd_verify)
    assert validate_args.strict_preview is True
    assert verify_args.strict_preview is True


def test_main_dispatches_strict_preview_to_validate_and_verify_handlers(
    monkeypatch,
) -> None:
    from maid_runner.cli.commands import validate as validate_cmd
    from maid_runner.cli.commands import verify as verify_cmd
    from maid_runner.cli.commands._main import main

    seen: list[tuple[str, bool]] = []

    def fake_validate(args: argparse.Namespace) -> int:
        seen.append(("validate", args.strict_preview))
        return 0

    def fake_verify(args: argparse.Namespace) -> int:
        seen.append(("verify", args.strict_preview))
        return 0

    monkeypatch.setattr(validate_cmd, "cmd_validate", fake_validate)
    monkeypatch.setattr(verify_cmd, "cmd_verify", fake_verify)

    assert main(["validate", "--strict-preview"]) == 0
    assert main(["verify", "--strict-preview"]) == 0
    assert seen == [("validate", True), ("verify", True)]


def test_validate_strict_preview_enables_strict_gates_and_labels_text(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "value"
""",
        test="""
from src.target import target


def test_calls_target_without_assertions():
    target()
""",
    )
    monkeypatch.chdir(tmp_path)

    default_exit = main(
        [
            "validate",
            str(manifest_path.relative_to(tmp_path)),
            "--mode",
            "behavioral",
            "--no-chain",
        ]
    )
    assert default_exit == 0
    assert "[strict-preview]" not in capsys.readouterr().out

    preview_exit = main(
        [
            "validate",
            str(manifest_path.relative_to(tmp_path)),
            "--mode",
            "behavioral",
            "--no-chain",
            "--strict-preview",
        ]
    )

    assert preview_exit == 1
    preview_output = capsys.readouterr().out
    assert preview_output.startswith("[strict-preview] FAIL target")
    assert "E210" in preview_output


def test_validate_strict_preview_json_marks_and_enables_artifact_coverage(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    manifest_path = _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_mentions_target_without_executing_body():
    assert target is not None
""",
    )
    monkeypatch.chdir(tmp_path)

    default_exit = main(
        [
            "validate",
            str(manifest_path.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--no-chain",
            "--json",
        ]
    )
    default_payload = json.loads(capsys.readouterr().out)

    preview_exit = main(
        [
            "validate",
            str(manifest_path.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--no-chain",
            "--strict-preview",
            "--json",
        ]
    )
    preview_payload = json.loads(capsys.readouterr().out)

    assert default_exit == 0
    assert "strict_preview" not in default_payload
    assert preview_exit == 1
    assert preview_payload["strict_preview"] is True
    assert preview_payload["artifact_coverage"]["success"] is False
    assert preview_payload["artifact_coverage"]["errors"][0]["code"] == "E710"


def test_validate_strict_preview_coherence_json_keeps_top_level_marker(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands import validate as validate_cmd
    from maid_runner.cli.commands._main import main
    from maid_runner.coherence.result import CoherenceResult

    _write_project(
        tmp_path,
        source="""
def target() -> str:
    return "executed"
""",
        test="""
from src.target import target


def test_executes_target_body():
    assert target() == "executed"
""",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        validate_cmd,
        "run_coherence",
        lambda manifest_dir, json_mode: CoherenceResult(checks_run=["fake"]),
    )

    exit_code = main(
        [
            "validate",
            "--manifest-dir",
            "manifests/",
            "--mode",
            "schema",
            "--coherence",
            "--strict-preview",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["strict_preview"] is True
    assert payload["validation"]["success"] is True
    assert "strict_preview" not in payload["validation"]
    assert payload["coherence"]["success"] is True


def test_validate_strict_preview_coherence_only_labels_text_and_json(
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands import validate as validate_cmd
    from maid_runner.cli.commands._main import main
    from maid_runner.coherence.result import CoherenceResult

    monkeypatch.setattr(
        validate_cmd,
        "run_coherence",
        lambda manifest_dir, json_mode: CoherenceResult(checks_run=["fake"]),
    )

    text_exit = main(["validate", "--coherence-only", "--strict-preview"])
    text_output = capsys.readouterr().out

    json_exit = main(["validate", "--coherence-only", "--strict-preview", "--json"])
    json_payload = json.loads(capsys.readouterr().out)

    assert text_exit == 0
    assert text_output.startswith("[strict-preview] ")
    assert json_exit == 0
    assert json_payload["strict_preview"] is True
    assert json_payload["success"] is True


def test_verify_strict_preview_forwards_artifact_coverage_and_labels_outputs(
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import VerificationResult

    seen: list[bool] = []

    def fake_run_verify(**kwargs):
        seen.append(kwargs["artifact_coverage"])
        return VerificationResult(stages=(), duration_ms=1.0)

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    for json_mode, summary in (
        (False, False),
        (False, True),
        (True, False),
        (True, True),
    ):
        exit_code = cmd_verify(
            _verify_args(strict_preview=True, json=json_mode, summary=summary)
        )
        assert exit_code == 0
        output = capsys.readouterr().out
        if json_mode:
            payload = json.loads(output)
            assert payload["strict_preview"] is True
        else:
            assert output.startswith("[strict-preview] ")

    assert seen == [True, True, True, True]


def test_verify_strict_preview_rejects_advisory(capsys) -> None:
    from maid_runner.cli.commands._main import main

    exit_code = main(["verify", "--strict-preview", "--advisory"])

    assert exit_code == 2
    assert "contradictory" in capsys.readouterr().err


def test_verify_strict_preview_warning_policy_keeps_info_e307_nonblocking(
    tmp_path: Path,
) -> None:
    from maid_runner.cli.commands.verify import _has_blocking_validation_warnings
    from maid_runner.core.result import (
        BatchValidationResult,
        ErrorCode,
        Location,
        Severity,
        ValidationError,
        ValidationResult,
    )
    from maid_runner.core.types import ValidationMode

    manifest_path = tmp_path / "manifests" / "info.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        'schema: "2"\ngoal: "Info"\ntype: feature\ncreated: "2026-07-04"\n',
    )
    warning = ValidationError(
        code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
        message="No validator available for recognized non-code file",
        severity=Severity.INFO,
        location=Location(file="package-lock.json"),
    )
    validation = ValidationResult(
        success=True,
        manifest_slug="info",
        manifest_path=str(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        warnings=[warning],
    )
    batch = BatchValidationResult(
        results=[validation],
        total_manifests=1,
        passed=1,
        failed=0,
        skipped=0,
    )

    assert (
        _has_blocking_validation_warnings(
            batch,
            project_root=tmp_path,
            fail_on_warnings=True,
        )
        is False
    )


def test_verify_without_strict_preview_keeps_outputs_unmarked(
    monkeypatch, capsys
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import VerificationResult

    def fake_run_verify(**kwargs):
        return VerificationResult(stages=(), duration_ms=1.0)

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    assert cmd_verify(_verify_args(strict_preview=False, json=True, summary=False)) == 0
    json_payload = json.loads(capsys.readouterr().out)
    assert "strict_preview" not in json_payload

    assert cmd_verify(_verify_args(strict_preview=False, json=False, summary=True)) == 0
    text_output = capsys.readouterr().out
    assert "[strict-preview]" not in text_output


def _verify_args(
    *,
    strict_preview: bool,
    json: bool,
    summary: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        manifest_dir="manifests/",
        allow_empty=False,
        fail_fast=True,
        strict=False,
        fail_on_warnings=False,
        advisory=False,
        worktree_scope=False,
        changed_scope=False,
        changed_scope_explicit=False,
        since=None,
        base_ref=None,
        include_tests=False,
        test_jobs=1,
        require_plan_lock=False,
        require_red_evidence=False,
        artifact_coverage=False,
        knockout=False,
        knockout_limit=None,
        knockout_allow_dirty=False,
        strict_preview=strict_preview,
        json=json,
        summary=summary,
        sarif=None,
        packet=None,
    )


def _write_project(
    root: Path,
    *,
    source: str,
    test: str,
) -> Path:
    src_dir = root / "src"
    tests_dir = root / "tests"
    manifests_dir = root / "manifests"
    src_dir.mkdir()
    tests_dir.mkdir()
    manifests_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "target.py").write_text(source.lstrip())
    (tests_dir / "test_target.py").write_text(test.lstrip())
    manifest_path = manifests_dir / "target.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Cover target"
type: feature
created: "2026-07-04T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: str
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
""",
    )
    return manifest_path
