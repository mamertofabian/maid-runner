"""Tests for CLI 'maid verify' command."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import os
import textwrap

import pytest
import yaml


def _write_verify_project(
    tmp_path,
    *,
    slug: str = "verify-gate",
    test_source: str | None = None,
    validate_command: str | None = None,
    created: str | None = None,
):
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    (src_dir / "gate.py").write_text(
        "def gate() -> str:\n    value = 'ok'\n    return value\n"
    )
    if test_source is None:
        test_source = (
            "from src.gate import gate\n\ndef test_gate():\n    assert gate() == 'ok'\n"
        )
    (tests_dir / "test_gate.py").write_text(test_source)

    manifest = {
        "schema": "2",
        "goal": "Verify the project gate",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/gate.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "gate",
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": ["tests/test_gate.py"],
        },
        "validate": [validate_command or "python -m pytest tests/test_gate.py -q"],
    }
    if created is not None:
        manifest["created"] = created
    manifest_path = manifest_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    return manifest_path


def _write_pyproject_pytest_addopts(tmp_path, addopts: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [tool.pytest.ini_options]
            addopts = {addopts}
            """
        )
    )


def _commit_all(project_dir, message: str = "commit") -> str:
    import subprocess

    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            message,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _without_durations(value):
    if isinstance(value, dict):
        return {
            key: _without_durations(item)
            for key, item in value.items()
            if key != "duration_ms"
        }
    if isinstance(value, list):
        return [_without_durations(item) for item in value]
    return value


def test_verify_parser_accepts_test_jobs_option():
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    args = parser.parse_args(["verify", "--test-jobs", "4", "--keep-going"])

    assert args.test_jobs == 4
    assert args.fail_fast is False


def test_verify_parser_rejects_invalid_test_jobs_option():
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()

    for value in ("0", "-1", "not-an-int"):
        with pytest.raises(SystemExit):
            parser.parse_args(["verify", "--test-jobs", value])


def test_verify_passes_test_jobs_to_tests_stage(tmp_path, monkeypatch):
    from maid_runner.cli.commands.verify import _tests_stage
    from maid_runner.core.result import BatchTestResult

    captured = {}

    def fake_integrity_errors(*args, **kwargs):
        return []

    def fake_run_tests(**kwargs):
        captured["jobs"] = kwargs["jobs"]
        return BatchTestResult(results=[], total=0, passed=0, failed=0)

    monkeypatch.setattr(
        "maid_runner.cli.commands.validate._validate_command_integrity_for_manifest_dir",
        fake_integrity_errors,
    )
    monkeypatch.setattr("maid_runner.core.test_runner.run_tests", fake_run_tests)

    stage = _tests_stage(tmp_path, "manifests/", fail_fast=False, test_jobs=3)

    assert stage.success is True
    assert captured["jobs"] == 3


def test_cmd_verify_forwards_test_jobs_to_run_verify(monkeypatch, capsys):
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import VerificationResult

    captured = {}

    def fake_run_verify(**kwargs):
        captured["test_jobs"] = kwargs["test_jobs"]
        captured["fail_fast"] = kwargs["fail_fast"]
        return VerificationResult(stages=(), duration_ms=1.0)

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = cmd_verify(
        argparse.Namespace(
            manifest_dir="manifests/",
            allow_empty=False,
            fail_fast=False,
            strict=False,
            fail_on_warnings=False,
            advisory=False,
            worktree_scope=False,
            changed_scope=False,
            since=None,
            base_ref=None,
            include_tests=False,
            test_jobs=3,
            json=False,
        )
    )

    assert exit_code == 0
    assert captured["test_jobs"] == 3
    assert captured["fail_fast"] is False


def test_cmd_verify_default_test_jobs_remains_serial(monkeypatch, capsys):
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.core.result import VerificationResult

    captured = {}

    def fake_run_verify(**kwargs):
        captured["test_jobs"] = kwargs["test_jobs"]
        return VerificationResult(stages=(), duration_ms=1.0)

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
            json=False,
        )
    )

    assert exit_code == 0
    assert captured["test_jobs"] == 1


def test_verify_returns_0_when_all_gates_pass(tmp_path, capsys):
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.verify import cmd_verify, run_verify

    os.chdir(tmp_path)
    _write_verify_project(tmp_path)

    result = run_verify("manifests/", tmp_path)
    assert result.stages
    assert all(stage.success for stage in result.stages)
    assert callable(cmd_verify)

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    for stage in ("schema", "behavioral", "implementation", "coherence"):
        assert f"PASS {stage}" in output
    assert "PASS file_tracking" in output
    assert "PASS tests" in output


def test_verify_returns_1_when_behavioral_validation_fails(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-behavioral-fail",
        test_source=textwrap.dedent(
            """\
            def test_placeholder():
                assert True
            """
        ),
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "PASS schema" in output
    assert "FAIL behavioral" in output
    assert "Artifact 'gate'" in output


def test_verify_default_fails_when_test_has_no_assertions(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-no-assertions",
        test_source=("from src.gate import gate\n\ndef test_gate():\n    gate()\n"),
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "FAIL behavioral" in output
    assert "E210" in output
    assert "test_gate" in output


def test_verify_advisory_mode_allows_missing_assertion_warning(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-advisory-no-assertions",
        test_source=("from src.gate import gate\n\ndef test_gate():\n    gate()\n"),
    )

    exit_code = main(["verify", "--advisory", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS behavioral" in output
    assert "E210" in output
    assert "test_gate" in output


def test_verify_legacy_manifest_warning_is_quiet_by_default(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-legacy-no-assertions",
        created="2026-05-16",
        test_source=("from src.gate import gate\n\ndef test_gate():\n    gate()\n"),
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS behavioral" in output
    assert "E118" not in output
    assert "E210" in output
    assert "test_gate" in output


def test_verify_legacy_manifest_warning_is_advisory_by_default(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-legacy-no-assertions",
        created="2026-05-16",
        test_source=("from src.gate import gate\n\ndef test_gate():\n    gate()\n"),
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS behavioral" in output
    assert "E118" not in output
    assert "E210" in output
    assert "test_gate" in output


test_verify_legacy_manifest_warning_is_advisory_by_default.__test__ = False


def test_verify_created_timestamp_chain_warning_is_advisory_by_default(
    tmp_path, capsys
):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-current-date-only",
        created="2026-06-03",
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "E118" in output


def test_verify_duplicate_created_chain_warning_is_advisory_by_default(
    tmp_path, capsys
):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-duplicate-created",
        created="2026-06-03T00:00:00+00:00",
    )
    (tmp_path / "src" / "other.py").write_text(
        "def other() -> str:\n    value = 'ok'\n    return value\n"
    )
    (tmp_path / "tests" / "test_other.py").write_text(
        "from src.other import other\n\ndef test_other():\n    assert other() == 'ok'\n"
    )
    (tmp_path / "manifests" / "verify-duplicate-created-read.manifest.yaml").write_text(
        yaml.dump(
            {
                "schema": "2",
                "goal": "Duplicate created warning",
                "type": "feature",
                "created": "2026-06-03T00:00:00+00:00",
                "files": {
                    "create": [
                        {
                            "path": "src/other.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "other",
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": ["tests/test_other.py"],
                },
                "validate": ["python -m pytest tests/test_other.py -q"],
            }
        )
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "E119" in output
    assert "falls back to slug" in output


def test_verify_validator_unavailable_warning_is_advisory_by_default(
    tmp_path,
):
    from maid_runner.cli.commands.verify import _warnings_are_blocking
    from maid_runner.core.result import ErrorCode, Severity, ValidationError

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "schema": "2",
        "goal": "Document workflow",
        "type": "feature",
        "created": "2026-05-20",
        "files": {
            "edit": [
                {
                    "path": "README.md",
                    "artifacts": [
                        {
                            "kind": "attribute",
                            "name": "workflow_docs",
                            "of": "docs",
                            "type": "section",
                        }
                    ],
                }
            ],
            "read": ["tests/test_gate.py"],
        },
        "validate": ["python -m pytest tests/test_gate.py -q"],
    }
    manifest_path = manifest_dir / "document-workflow.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    warnings = [
        ValidationError(
            code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
            message="No validator available for 'README.md'",
            severity=Severity.WARNING,
        )
    ]

    assert _warnings_are_blocking(warnings, str(manifest_path), tmp_path) is False


def test_verify_base_validator_default_hook_stub_warning_is_advisory_by_default(
    tmp_path,
):
    from maid_runner.cli.commands.verify import _warnings_are_blocking
    from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "schema": "2",
        "goal": "Keep BaseValidator default hook warnings advisory",
        "type": "fix",
        "created": "2026-05-25",
        "files": {
            "edit": [
                {
                    "path": "maid_runner/validators/base.py",
                    "artifacts": [
                        {
                            "kind": "method",
                            "name": "module_path",
                            "of": "BaseValidator",
                        }
                    ],
                }
            ],
            "read": ["tests/cli/test_verify_cmd.py"],
        },
        "validate": ["python -m pytest tests/cli/test_verify_cmd.py -q"],
    }
    manifest_path = manifest_dir / "base-validator-default-hooks.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    warnings = [
        ValidationError(
            code=ErrorCode.STUB_FUNCTION_DETECTED,
            message=(
                "Function 'BaseValidator.module_path' appears to be a stub "
                "in maid_runner/validators/base.py"
            ),
            severity=Severity.WARNING,
            location=Location(file="maid_runner/validators/base.py", line=128),
        )
    ]

    assert _warnings_are_blocking(warnings, str(manifest_path), tmp_path) is False


def test_verify_non_default_stub_warning_remains_blocking(tmp_path):
    from maid_runner.cli.commands.verify import _warnings_are_blocking
    from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "schema": "2",
        "goal": "Keep real stub warnings blocking",
        "type": "fix",
        "created": "2026-05-25",
        "files": {
            "create": [
                {
                    "path": "src/worker.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "run",
                        }
                    ],
                }
            ],
            "read": ["tests/test_worker.py"],
        },
        "validate": ["python -m pytest tests/test_worker.py -q"],
    }
    manifest_path = manifest_dir / "real-stub.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    warnings = [
        ValidationError(
            code=ErrorCode.STUB_FUNCTION_DETECTED,
            message="Function 'run' appears to be a stub in src/worker.py",
            severity=Severity.WARNING,
            location=Location(file="src/worker.py", line=1),
        )
    ]

    assert _warnings_are_blocking(warnings, str(manifest_path), tmp_path) is True


def test_verify_base_validator_default_hook_prefix_stub_warning_remains_blocking(
    tmp_path,
):
    from maid_runner.cli.commands.verify import _warnings_are_blocking
    from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "schema": "2",
        "goal": "Keep only exact BaseValidator default hooks advisory",
        "type": "fix",
        "created": "2026-05-25",
        "files": {
            "edit": [
                {
                    "path": "maid_runner/validators/base.py",
                    "artifacts": [
                        {
                            "kind": "method",
                            "name": "module_path_extra",
                            "of": "BaseValidator",
                        }
                    ],
                }
            ],
            "read": ["tests/cli/test_verify_cmd.py"],
        },
        "validate": ["python -m pytest tests/cli/test_verify_cmd.py -q"],
    }
    manifest_path = manifest_dir / "base-validator-prefix-stub.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    warnings = [
        ValidationError(
            code=ErrorCode.STUB_FUNCTION_DETECTED,
            message=(
                "Function 'BaseValidator.module_path_extra' appears to be a stub "
                "in maid_runner/validators/base.py"
            ),
            severity=Severity.WARNING,
            location=Location(file="maid_runner/validators/base.py", line=128),
        )
    ]

    assert _warnings_are_blocking(warnings, str(manifest_path), tmp_path) is True


def test_verify_base_validator_default_hook_wrong_path_remains_blocking(tmp_path):
    from maid_runner.cli.commands.verify import _warnings_are_blocking
    from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "schema": "2",
        "goal": "Keep wrong-path BaseValidator hooks blocking",
        "type": "fix",
        "created": "2026-05-25",
        "files": {
            "create": [
                {
                    "path": "vendor/maid_runner/validators/base.py",
                    "artifacts": [
                        {
                            "kind": "method",
                            "name": "module_path",
                            "of": "BaseValidator",
                        }
                    ],
                }
            ],
            "read": ["tests/cli/test_verify_cmd.py"],
        },
        "validate": ["python -m pytest tests/cli/test_verify_cmd.py -q"],
    }
    manifest_path = manifest_dir / "vendored-base-validator.manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    warnings = [
        ValidationError(
            code=ErrorCode.STUB_FUNCTION_DETECTED,
            message=(
                "Function 'BaseValidator.module_path' appears to be a stub "
                "in vendor/maid_runner/validators/base.py"
            ),
            severity=Severity.WARNING,
            location=Location(file="vendor/maid_runner/validators/base.py", line=128),
        )
    ]

    assert _warnings_are_blocking(warnings, str(manifest_path), tmp_path) is True


def test_verify_ignores_pytest_fixture_helpers_named_like_tests(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-fixture-helper",
        test_source=(
            "import pytest\n"
            "from src.gate import gate\n\n"
            "@pytest.fixture\n"
            "def test_gate_value():\n"
            "    return gate()\n\n"
            "def test_gate(test_gate_value):\n"
            "    assert test_gate_value == 'ok'\n"
        ),
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "E210" not in output


def test_verify_json_preserves_missing_assertion_details(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-json-no-assertions",
        test_source=("from src.gate import gate\n\ndef test_gate():\n    gate()\n"),
    )

    exit_code = main(["verify", "--json"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    warnings = stages["behavioral"]["details"]["results"][0]["warnings"]
    assert warnings[0]["code"] == "E210"
    assert warnings[0]["severity"] == "warning"
    assert warnings[0]["location"]["file"] == "tests/test_gate.py"


def test_verify_returns_1_when_manifest_validate_command_fails(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-test-fail",
        test_source=(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n"
        ),
        validate_command="python -m pytest tests/test_gate.py -q",
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "PASS implementation" in output
    assert "FAIL tests" in output
    assert "FAIL [verify-test-fail]" in output
    assert "exit 1" in output


def test_verify_rejects_noop_validate_command_for_behavioral_tests(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-noop",
        validate_command='python -c "raise SystemExit(0)"',
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "FAIL tests" in output
    assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in output
    assert "python -c" in output


def test_verify_rejects_pytest_config_collect_only(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-pyproject-collect-only",
        test_source=(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n"
        ),
        validate_command="python -m pytest tests -q",
    )
    _write_pyproject_pytest_addopts(tmp_path, '"--collect-only"')

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "FAIL tests" in output
    assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in output
    assert "pyproject.toml" in output
    assert "--collect-only" in output


def test_verify_rejects_pytest_config_selector_deselecting_behavioral_test(
    tmp_path, capsys
):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-pyproject-selector",
        test_source=(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        ),
        validate_command="python -m pytest tests -q",
    )
    _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "FAIL tests" in output
    assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in output
    assert "pyproject.toml" in output
    assert "-k test_other" in output


def test_verify_json_reports_pytest_config_addopts_integrity_error(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-json-pyproject-selector",
        test_source=(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        ),
        validate_command="python -m pytest tests -q",
    )
    _write_pyproject_pytest_addopts(tmp_path, '"-k test_other"')

    exit_code = main(["verify", "--no-changed-scope", "--keep-going", "--json"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    errors = stages["tests"]["details"]["errors"]
    assert errors[0]["code"] == "E230"
    assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in errors[0]["message"]
    assert "pyproject.toml" in errors[0]["message"]


def test_verify_rejects_runner_name_that_is_not_invoked(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-echo-runner-name",
        validate_command="echo pytest tests/test_gate.py",
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "FAIL tests" in output
    assert "VALIDATE_COMMAND_DOES_NOT_RUN_TESTS" in output
    assert "echo pytest tests/test_gate.py" in output


def test_verify_accepts_test_runner_validate_command(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-test-runner",
        validate_command="python -m pytest tests -q",
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS tests" in output


def test_verify_allow_empty_returns_0_without_manifest_directory(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)

    exit_code = main(["verify", "--allow-empty"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS schema" in output
    assert "PASS coherence" in output
    assert "Skipped because --allow-empty found no active manifests" in output


def test_verify_json_worktree_scope_reports_structured_errors(tmp_path, capsys):
    import subprocess

    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path, slug="verify-worktree-json")
    (tmp_path / "src" / "extra.py").write_text(
        "def extra() -> str:\n    return 'drift'\n"
    )
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

    exit_code = main(
        ["verify", "--json", "--keep-going", "--worktree-scope", "--no-changed-scope"]
    )

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    worktree_errors = stages["worktree_scope"]["details"]["errors"]
    assert worktree_errors[0]["code"] == "E114"
    assert worktree_errors[0]["location"]["file"] == "src/extra.py"
    assert "outside writable manifest scope" in worktree_errors[0]["message"]


def test_verify_changed_scope_stage_reports_read_only_changed_file(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_verify_project(tmp_path, slug="verify-changed-scope")
    baseline = _commit_all(tmp_path, "baseline")
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["metadata"] = {"maid_task_base": baseline}
    manifest["files"]["read"].append("src/gate.py")
    manifest["files"]["create"][0]["path"] = "src/app.py"
    manifest["files"]["create"][0]["artifacts"][0]["name"] = "app"
    manifest["validate"] = ["python -m pytest tests/test_app.py -q"]
    manifest_path.write_text(yaml.dump(manifest))
    (tmp_path / "src" / "app.py").write_text(
        "def app() -> str:\n    value = 'ok'\n    return value\n"
    )
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import app\n\ndef test_app():\n    assert app() == 'ok'\n"
    )
    (tmp_path / "src" / "gate.py").write_text(
        "def gate() -> str:\n    return 'changed'\n"
    )

    exit_code = main(["verify", "--keep-going", "--json"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    errors = stages["changed_scope"]["details"]["errors"]
    assert errors[0]["code"] == "E114"
    assert errors[0]["location"]["file"] == "src/gate.py"


def test_verify_default_changed_scope_requires_baseline(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path, slug="verify-changed-scope-default")

    exit_code = main(["verify", "--keep-going", "--json"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    errors = stages["changed_scope"]["details"]["errors"]
    assert errors[0]["code"] == "E115"
    assert "origin/main" not in errors[0]["message"]


def test_verify_changed_scope_stage_passes_with_since_for_writable_changes(
    tmp_path,
    capsys,
):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path, slug="verify-changed-scope-pass")
    baseline = _commit_all(tmp_path, "baseline")
    (tmp_path / "src" / "gate.py").write_text(
        "def gate() -> str:\n    value = 'ok'\n    return value\n# changed\n"
    )

    exit_code = main(["verify", "--since", baseline, "--keep-going"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "PASS changed_scope" in output
    assert "PASS tests" in output


def test_verify_shares_one_manifest_chain_across_stages(tmp_path, monkeypatch):
    import importlib
    import subprocess

    from maid_runner.cli.commands import validate as validate_command
    from maid_runner.cli.commands.verify import _run_verify
    from maid_runner.core import chain as chain_module
    from maid_runner.core import test_runner

    validate_module = importlib.import_module("maid_runner.core.validate")

    os.chdir(tmp_path)
    manifest_path = _write_verify_project(tmp_path, slug="verify-shared-chain")
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["type"] = "snapshot"
    manifest["validate"] = [
        "uv run maid validate manifests/verify-shared-chain.manifest.yaml --mode schema"
    ]
    manifest_path.write_text(yaml.dump(manifest))
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

    constructed = 0
    integrity_calls = 0
    test_runner_calls = 0
    original_chain = chain_module.ManifestChain
    original_integrity = validate_command._validate_command_integrity_for_manifest_dir
    original_run_tests = test_runner.run_tests

    class CountingManifestChain(original_chain):
        def __init__(self, *args, **kwargs):
            nonlocal constructed
            constructed += 1
            super().__init__(*args, **kwargs)

    def counting_integrity(*args, **kwargs):
        nonlocal integrity_calls
        integrity_calls += 1
        return original_integrity(*args, **kwargs)

    def counting_run_tests(*args, **kwargs):
        nonlocal test_runner_calls
        test_runner_calls += 1
        return original_run_tests(*args, **kwargs)

    monkeypatch.setattr(chain_module, "ManifestChain", CountingManifestChain)
    monkeypatch.setattr(validate_module, "ManifestChain", CountingManifestChain)
    monkeypatch.setattr(
        validate_command,
        "_validate_command_integrity_for_manifest_dir",
        counting_integrity,
    )
    monkeypatch.setattr(test_runner, "run_tests", counting_run_tests)
    chain_module.clear_manifest_chain_cache()
    try:
        result = _run_verify(
            manifest_dir="manifests",
            project_root=tmp_path,
            check_assertions=True,
            check_stubs=True,
            fail_on_warnings=True,
            require_worktree_scope=True,
            require_changed_scope=False,
        )
    finally:
        chain_module.clear_manifest_chain_cache()

    assert all(stage.success for stage in result.stages)
    assert integrity_calls == 1
    assert test_runner_calls == 1
    assert constructed == 1


def test_verify_reuses_validation_cache_across_behavioral_and_implementation_stages(
    tmp_path,
    monkeypatch,
):
    from maid_runner.cli.commands.verify import _run_verify
    from maid_runner.core import ts_module_paths
    from maid_runner.core.result import BatchValidationResult
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    compiler_calls = []

    def compiler_resolver(module, name, root):
        compiler_calls.append((module, name, root))
        return ("src/button", "Button")

    def validating_stage(self, manifest_dir, *, mode, **kwargs):
        if mode in (ValidationMode.BEHAVIORAL, ValidationMode.IMPLEMENTATION):
            assert ts_module_paths.resolve_ts_reexport(
                "src/components", "Button", tmp_path
            ) == (
                "src/button",
                "Button",
            )
        return BatchValidationResult(
            results=[],
            total_manifests=0,
            passed=0,
            failed=0,
            skipped=0,
            duration_ms=0,
        )

    ts_module_paths.clear_ts_resolution_cache()
    monkeypatch.setattr(
        ts_module_paths,
        "resolve_reexport_with_compiler",
        compiler_resolver,
    )
    monkeypatch.setattr(ValidationEngine, "validate_all", validating_stage)

    result = _run_verify(
        manifest_dir="manifests",
        project_root=tmp_path,
        allow_empty=True,
        check_assertions=True,
        check_stubs=True,
        fail_on_warnings=True,
        require_worktree_scope=False,
        require_changed_scope=False,
    )

    assert all(stage.success for stage in result.stages)
    assert [(module, name) for module, name, _ in compiler_calls] == [
        ("src/components", "Button")
    ]


def test_verify_json_output_matches_without_shared_cache_except_durations(
    tmp_path,
    monkeypatch,
):
    from maid_runner.cli.commands._format import format_verify_result
    from maid_runner.cli.commands.verify import _run_verify
    from maid_runner.core.validate import ValidationEngine

    os.chdir(tmp_path)
    _write_verify_project(tmp_path, slug="verify-cache-equivalence")

    shared = _run_verify(
        manifest_dir="manifests",
        project_root=tmp_path,
        check_assertions=True,
        check_stubs=True,
        fail_on_warnings=True,
        require_worktree_scope=False,
        require_changed_scope=False,
    )
    monkeypatch.setattr(
        ValidationEngine,
        "validation_cache_scope",
        lambda self: nullcontext(),
    )
    legacy = _run_verify(
        manifest_dir="manifests",
        project_root=tmp_path,
        check_assertions=True,
        check_stubs=True,
        fail_on_warnings=True,
        require_worktree_scope=False,
        require_changed_scope=False,
    )

    shared_payload = json.loads(format_verify_result(shared, json_mode=True))
    legacy_payload = json.loads(format_verify_result(legacy, json_mode=True))
    assert _without_durations(shared_payload) == _without_durations(legacy_payload)


def test_verify_cache_scope_clears_after_command(tmp_path, monkeypatch):
    from maid_runner.cli.commands.verify import _run_verify
    from maid_runner.core import ts_module_paths
    from maid_runner.core.result import BatchValidationResult
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    state = {"target": ("src/old-button", "Button")}
    compiler_calls = []

    def compiler_resolver(module, name, root):
        compiler_calls.append((module, name, state["target"]))
        return state["target"]

    def validating_stage(self, manifest_dir, *, mode, **kwargs):
        if mode == ValidationMode.BEHAVIORAL:
            assert ts_module_paths.resolve_ts_reexport(
                "src/components", "Button", tmp_path
            ) == (
                "src/old-button",
                "Button",
            )
        return BatchValidationResult(
            results=[],
            total_manifests=0,
            passed=0,
            failed=0,
            skipped=0,
            duration_ms=0,
        )

    ts_module_paths.clear_ts_resolution_cache()
    monkeypatch.setattr(
        ts_module_paths,
        "resolve_reexport_with_compiler",
        compiler_resolver,
    )
    monkeypatch.setattr(ValidationEngine, "validate_all", validating_stage)

    result = _run_verify(
        manifest_dir="manifests",
        project_root=tmp_path,
        allow_empty=True,
        check_assertions=True,
        check_stubs=True,
        fail_on_warnings=True,
        require_worktree_scope=False,
        require_changed_scope=False,
    )
    state["target"] = ("src/new-button", "Button")

    assert all(stage.success for stage in result.stages)
    assert ts_module_paths.resolve_ts_reexport(
        "src/components", "Button", tmp_path
    ) == (
        "src/new-button",
        "Button",
    )
    assert [target for _, _, target in compiler_calls] == [
        ("src/old-button", "Button"),
        ("src/new-button", "Button"),
    ]


def test_verify_json_reports_all_stage_statuses(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path, slug="verify-json")

    exit_code = main(["verify", "--json", "--no-changed-scope"])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    stages = {stage["name"]: stage for stage in data["stages"]}
    for stage in (
        "schema",
        "behavioral",
        "implementation",
        "coherence",
        "file_tracking",
        "tests",
    ):
        assert stages[stage]["success"] is True
    assert stages["tests"]["details"]["total"] == 1
