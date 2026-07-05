from __future__ import annotations

import json
import os
import subprocess

import yaml


def _commit_all(project_dir, message: str = "commit") -> str:
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


def _write_verify_project(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src" / "gate.py").write_text(
        "def gate() -> str:\n    value = 'ok'\n    return value\n"
    )
    (tmp_path / "tests" / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_gate():\n"
        "    assert gate() == 'ok'\n"
    )
    manifest = {
        "schema": "2",
        "goal": "Verify clean changed-scope skip",
        "type": "feature",
        "created": "2026-07-03T00:00:00Z",
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
        "validate": ["python -m pytest tests/test_gate.py -q"],
    }
    (tmp_path / "manifests" / "verify-skip.manifest.yaml").write_text(
        yaml.dump(manifest)
    )


def test_bare_verify_passes_with_visible_skip_on_clean_tree(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path)
    _commit_all(tmp_path, "baseline")

    exit_code = main(["verify"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SKIPPED changed_scope" in output
    assert "no baseline; clean tree" in output
    assert "FAIL changed_scope" not in output
    assert "PASS changed_scope" not in output


def test_bare_verify_still_fails_e115_on_dirty_tree(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path)
    _commit_all(tmp_path, "baseline")
    (tmp_path / "src" / "gate.py").write_text(
        "def gate() -> str:\n    return 'changed'\n"
    )

    exit_code = main(["verify", "--keep-going", "--json"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    errors = stages["changed_scope"]["details"]["errors"]
    assert errors[0]["code"] == "E115"
    assert stages["changed_scope"].get("skip_reason") is None


def test_explicit_changed_scope_flag_keeps_e115_on_clean_tree(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_verify_project(tmp_path)
    _commit_all(tmp_path, "baseline")

    exit_code = main(["verify", "--changed-scope", "--keep-going", "--json"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in data["stages"]}
    errors = stages["changed_scope"]["details"]["errors"]
    assert errors[0]["code"] == "E115"
    assert stages["changed_scope"].get("skip_reason") is None


def test_json_and_summary_represent_skip_explicitly(tmp_path, capsys):
    from maid_runner.cli.commands._main import main

    json_project = tmp_path / "json"
    json_project.mkdir()
    os.chdir(json_project)
    _write_verify_project(json_project)
    _commit_all(json_project, "baseline")

    json_exit = main(["verify", "--json"])
    default_payload = json.loads(capsys.readouterr().out)

    summary_project = tmp_path / "summary"
    summary_project.mkdir()
    os.chdir(summary_project)
    _write_verify_project(summary_project)
    _commit_all(summary_project, "baseline")

    summary_exit = main(["verify", "--summary", "--json"])
    summary_payload = json.loads(capsys.readouterr().out)

    assert json_exit == summary_exit == 0
    default_stages = {stage["name"]: stage for stage in default_payload["stages"]}
    assert default_stages["changed_scope"]["skip_reason"] == ("no baseline; clean tree")
    assert "changed_scope" in summary_payload["skipped_stages"]
    assert "changed_scope" not in summary_payload["passed_stages"]
