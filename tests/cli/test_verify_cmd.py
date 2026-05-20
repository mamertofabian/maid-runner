"""Tests for CLI 'maid verify' command."""

from __future__ import annotations

import json
import os
import textwrap

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
        test_source=(
            "from src.gate import gate\n\n" "def test_gate():\n" "    gate()\n"
        ),
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
        test_source=(
            "from src.gate import gate\n\n" "def test_gate():\n" "    gate()\n"
        ),
    )

    exit_code = main(["verify", "--advisory", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS behavioral" in output
    assert "E210" in output
    assert "test_gate" in output


def test_verify_legacy_manifest_warning_is_advisory_by_default(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(
        tmp_path,
        slug="verify-legacy-no-assertions",
        created="2026-05-16",
        test_source=(
            "from src.gate import gate\n\n" "def test_gate():\n" "    gate()\n"
        ),
    )

    exit_code = main(["verify", "--no-changed-scope"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verify: PASS" in output
    assert "PASS behavioral" in output
    assert "E210" in output
    assert "test_gate" in output


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
        test_source=(
            "from src.gate import gate\n\n" "def test_gate():\n" "    gate()\n"
        ),
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
