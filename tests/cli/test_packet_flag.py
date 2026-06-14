from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml


def _write_project(root: Path, *, passing: bool, slug: str = "packet-task") -> Path:
    manifest_dir = root / "manifests"
    manifest_dir.mkdir()
    src_dir = root / "src"
    src_dir.mkdir()
    tests_dir = root / "tests"
    tests_dir.mkdir()
    source = "def gate() -> str:\n    return 'ok'\n" if passing else "# missing gate\n"
    (src_dir / "gate.py").write_text(source)
    (tests_dir / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_gate():\n"
        "    assert gate() == 'ok'\n"
    )
    manifest = {
        "schema": "2",
        "goal": "Exercise packet flag",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/gate.py",
                    "artifacts": [
                        {"kind": "function", "name": "gate", "returns": "str"}
                    ],
                }
            ],
            "read": ["tests/test_gate.py"],
        },
        "validate": ["python -m pytest tests/test_gate.py -q"],
    }
    manifest_path = manifest_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    return manifest_path


def test_build_parser_accepts_validate_and_verify_packet_options():
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()

    validate_args = parser.parse_args(["validate", "--packet"])
    verify_args = parser.parse_args(["verify", "--packet", "packet.json"])

    assert validate_args.packet == ".maid/last-failure-packet.json"
    assert verify_args.packet == "packet.json"


def test_main_validate_packet_writes_failure_packet_and_preserves_exit_code(
    tmp_path,
    capsys,
):
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.validate import cmd_validate

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    packet_path = tmp_path / "packet.json"

    without_packet = main(
        ["validate", str(manifest_path), "--mode", "implementation", "--no-chain"]
    )
    with_packet = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--packet",
            str(packet_path),
        ]
    )

    assert callable(cmd_validate)
    assert without_packet == 1
    assert with_packet == 1
    packet = json.loads(packet_path.read_text())
    assert set(packet) == {
        "packet_version",
        "command",
        "exit_code",
        "project_root",
        "manifest",
        "diagnostics",
        "test_output",
        "environment",
    }
    assert packet["exit_code"] == 1
    assert packet["command"][-2:] == ["--packet", str(packet_path)]
    assert packet["diagnostics"][0]["code"] == "E300"
    assert packet["diagnostics"][0]["message"]
    assert packet["diagnostics"][0]["next_action"]["kind"] == "edit-implementation"
    capsys.readouterr()


def test_validate_packet_diagnostics_match_json_output_one_to_one(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    packet_path = tmp_path / "packet.json"

    json_exit = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--json",
        ]
    )
    json_payload = json.loads(capsys.readouterr().out)
    packet_exit = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--packet",
            str(packet_path),
        ]
    )

    packet = json.loads(packet_path.read_text())
    json_diagnostics = [
        (item["code"], item["message"], item.get("location", {}).get("file"))
        for item in json_payload["errors"] + json_payload["warnings"]
    ]
    packet_diagnostics = [
        (item["code"], item["message"], item["file"]) for item in packet["diagnostics"]
    ]

    assert json_exit == packet_exit == 1
    assert packet_diagnostics == json_diagnostics


def test_validate_packet_clears_stale_file_on_success(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=True)
    packet_path = tmp_path / "packet.json"
    packet_path.write_text('{"stale": true}\n')

    exit_code = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--packet",
            str(packet_path),
        ]
    )

    assert exit_code == 0
    assert packet_path.exists() is False
    capsys.readouterr()


def test_validate_packet_uses_default_path_when_option_has_no_value(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)

    exit_code = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--packet",
        ]
    )

    assert exit_code == 1
    assert (tmp_path / ".maid" / "last-failure-packet.json").exists()
    capsys.readouterr()


def test_validate_packet_includes_failing_validate_command_output_tail(
    tmp_path,
    capsys,
):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=True)
    (tmp_path / "tests" / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_gate():\n"
        "    assert gate() == 'ok'\n"
        "    for index in range(60):\n"
        "        print(f'line-{index}')\n"
        "    assert False\n"
    )
    packet_path = tmp_path / "packet.json"

    exit_code = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--run-tests",
            "--packet",
            str(packet_path),
        ]
    )

    packet = json.loads(packet_path.read_text())

    assert exit_code == 1
    assert packet["manifest"][0]["path"] == "manifests/packet-task.manifest.yaml"
    assert packet["test_output"][0]["exit_code"] == 1
    assert len(packet["test_output"][0]["output_tail"].splitlines()) == 50
    assert "line-59" in packet["test_output"][0]["output_tail"]
    capsys.readouterr()


def test_validate_packet_write_failure_does_not_change_exit_code(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    packet_path = tmp_path / "packet-dir"
    packet_path.mkdir()

    exit_code = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--packet",
            str(packet_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Failed to prepare failure packet" in captured.err


def test_validate_coherence_failure_writes_packet(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands._main import main
    from maid_runner.coherence.result import (
        CoherenceIssue,
        CoherenceResult,
        IssueSeverity,
        IssueType,
    )

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=True)
    packet_path = tmp_path / "coherence-packet.json"

    def fake_run_coherence(manifest_dir, json_mode):
        return CoherenceResult(
            issues=[
                CoherenceIssue(
                    issue_type=IssueType.DUPLICATE,
                    severity=IssueSeverity.ERROR,
                    message="Duplicate artifact gate",
                    file="src/gate.py",
                    manifests=("packet-task",),
                )
            ],
            checks_run=["duplicate"],
        )

    monkeypatch.setattr(
        "maid_runner.cli.commands.validate.run_coherence",
        fake_run_coherence,
    )

    exit_code = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--coherence",
            "--packet",
            str(packet_path),
        ]
    )

    packet = json.loads(packet_path.read_text())

    assert exit_code == 1
    assert packet["manifest"][0]["path"] == "manifests/packet-task.manifest.yaml"
    assert packet["diagnostics"][0]["code"] == "E400"
    assert packet["diagnostics"][0]["message"] == "Duplicate artifact gate"
    capsys.readouterr()


def test_validate_coherence_only_packet_clears_stale_file_on_success(
    tmp_path,
    monkeypatch,
    capsys,
):
    from maid_runner.cli.commands._main import main
    from maid_runner.coherence.result import CoherenceResult

    os.chdir(tmp_path)
    _write_project(tmp_path, passing=True)
    packet_path = tmp_path / "coherence-packet.json"
    packet_path.write_text('{"stale": true}\n')

    def fake_run_coherence(manifest_dir, json_mode):
        return CoherenceResult(checks_run=["duplicate"])

    monkeypatch.setattr(
        "maid_runner.cli.commands.validate.run_coherence",
        fake_run_coherence,
    )

    exit_code = main(
        [
            "validate",
            "--coherence-only",
            "--packet",
            str(packet_path),
        ]
    )

    assert exit_code == 0
    assert packet_path.exists() is False
    capsys.readouterr()


def test_cmd_verify_writes_packet_for_failed_verify_run(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import (
        BatchValidationResult,
        ErrorCode,
        Location,
        ValidationError,
        ValidationResult,
        VerificationResult,
        VerificationStageResult,
    )
    from maid_runner.core.types import ValidationMode

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    packet_path = tmp_path / "verify-packet.json"
    validation = ValidationResult(
        success=False,
        manifest_slug="packet-task",
        manifest_path=str(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        errors=[
            ValidationError(
                code=ErrorCode.ARTIFACT_NOT_DEFINED,
                message="Artifact 'gate' not defined",
                location=Location(file="src/gate.py", line=1),
            )
        ],
    )
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="implementation",
                success=False,
                _validation=BatchValidationResult(
                    results=[validation],
                    total_manifests=1,
                    passed=0,
                    failed=1,
                    skipped=0,
                ),
            ),
        )
    )

    def fake_run_verify(**kwargs):
        return result

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = cmd_verify(
        argparse.Namespace(
            manifest_dir="manifests/",
            allow_empty=False,
            fail_fast=True,
            strict=False,
            fail_on_warnings=False,
            advisory=False,
            worktree_scope=False,
            changed_scope=False,
            since=None,
            base_ref=None,
            include_tests=False,
            test_jobs=1,
            require_plan_lock=False,
            require_red_evidence=False,
            json=False,
            packet=str(packet_path),
            _maid_argv=["maid", "verify", "--packet", str(packet_path)],
        )
    )

    packet = json.loads(packet_path.read_text())

    assert exit_code == 1
    assert packet["command"][1] == "verify"
    assert packet["diagnostics"][0]["code"] == "E300"
    assert packet["manifest"][0]["path"] == "manifests/packet-task.manifest.yaml"
    capsys.readouterr()


def test_cmd_verify_packet_write_failure_does_not_change_exit_code(
    tmp_path,
    monkeypatch,
    capsys,
):
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import (
        BatchValidationResult,
        ErrorCode,
        Location,
        ValidationError,
        ValidationResult,
        VerificationResult,
        VerificationStageResult,
    )
    from maid_runner.core.types import ValidationMode

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    packet_path = tmp_path / "verify-packet-dir"
    packet_path.mkdir()
    validation = ValidationResult(
        success=False,
        manifest_slug="packet-task",
        manifest_path=str(manifest_path),
        mode=ValidationMode.IMPLEMENTATION,
        errors=[
            ValidationError(
                code=ErrorCode.ARTIFACT_NOT_DEFINED,
                message="Artifact 'gate' not defined",
                location=Location(file="src/gate.py", line=1),
            )
        ],
    )

    def fake_run_verify(**kwargs):
        return VerificationResult(
            stages=(
                VerificationStageResult(
                    name="implementation",
                    success=False,
                    _validation=BatchValidationResult(
                        results=[validation],
                        total_manifests=1,
                        passed=0,
                        failed=1,
                        skipped=0,
                    ),
                ),
            )
        )

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = cmd_verify(
        argparse.Namespace(
            manifest_dir="manifests/",
            allow_empty=False,
            fail_fast=True,
            strict=False,
            fail_on_warnings=False,
            advisory=False,
            worktree_scope=False,
            changed_scope=False,
            since=None,
            base_ref=None,
            include_tests=False,
            test_jobs=1,
            require_plan_lock=False,
            require_red_evidence=False,
            json=False,
            packet=str(packet_path),
            _maid_argv=["maid", "verify", "--packet", str(packet_path)],
        )
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Failed to prepare failure packet" in captured.err


def test_cmd_verify_clears_stale_packet_on_success(tmp_path, monkeypatch, capsys):
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import VerificationResult, VerificationStageResult

    os.chdir(tmp_path)
    packet_path = tmp_path / "verify-packet.json"
    packet_path.write_text('{"stale": true}\n')

    def fake_run_verify(**kwargs):
        return VerificationResult(
            stages=(VerificationStageResult(name="schema", success=True),)
        )

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = cmd_verify(
        argparse.Namespace(
            manifest_dir="manifests/",
            allow_empty=False,
            fail_fast=True,
            strict=False,
            fail_on_warnings=False,
            advisory=False,
            worktree_scope=False,
            changed_scope=False,
            since=None,
            base_ref=None,
            include_tests=False,
            test_jobs=1,
            require_plan_lock=False,
            require_red_evidence=False,
            json=False,
            packet=str(packet_path),
            _maid_argv=["maid", "verify", "--packet", str(packet_path)],
        )
    )

    assert exit_code == 0
    assert packet_path.exists() is False
    capsys.readouterr()


def test_main_validate_packet_bytes_are_deterministic_for_same_failure(
    tmp_path,
    capsys,
):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    packet_path = tmp_path / "packet.json"
    argv = [
        "validate",
        str(manifest_path),
        "--mode",
        "implementation",
        "--no-chain",
        "--packet",
        str(packet_path),
    ]

    first_exit = main(argv)
    first_bytes = packet_path.read_bytes()
    second_exit = main(argv)
    second_bytes = packet_path.read_bytes()

    assert first_exit == second_exit == 1
    assert first_bytes == second_bytes
    assert b"cmd_validate" not in first_bytes
    assert "main" in Path(__file__).read_text()
    capsys.readouterr()


def test_packet_flag_test_module_mentions_cmd_validate_cmd_verify_build_parser_and_main():
    source = Path(__file__).read_text()

    assert "cmd_validate" in source
    assert "cmd_verify" in source
    assert "build_parser" in source
    assert "main" in source
