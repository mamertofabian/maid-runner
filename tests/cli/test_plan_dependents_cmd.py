"""Behavioral contract for shared-test plan-lock dependency discovery."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import create_plan_lock, default_plan_lock_path
from maid_runner.core.result import ErrorCode


def _manifest_text(
    slug: str,
    source_path: str,
    *,
    created: str,
    supersedes: str | None = None,
) -> str:
    supersedes_block = f"supersedes:\n  - {supersedes}\n" if supersedes else ""
    function_name = slug.replace("-", "_")
    return f"""schema: "2"
goal: "Provide {slug} behavior"
type: feature
created: "{created}"
{supersedes_block}files:
  create:
    - path: {source_path}
      artifacts:
        - kind: function
          name: {function_name}
          args: []
          returns: int
  read:
    - tests/test_shared.py
validate:
  - python -m pytest -q tests/test_shared.py
"""


def _write_shared_project(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_shared.py").write_text(
        "def test_shared_contract():\n    assert 1 + 2 == 3\n",
        encoding="utf-8",
    )
    alpha = tmp_path / "manifests" / "alpha.manifest.yaml"
    beta = tmp_path / "manifests" / "beta.manifest.yaml"
    alpha.write_text(
        _manifest_text("alpha", "src/alpha.py", created="2026-08-09T00:00:00Z"),
        encoding="utf-8",
    )
    beta.write_text(
        _manifest_text("beta", "src/beta.py", created="2026-08-09T00:01:00Z"),
        encoding="utf-8",
    )
    for manifest_path in (alpha, beta):
        lock = create_plan_lock(manifest_path, tmp_path)
        lock.save(default_plan_lock_path(tmp_path, manifest_path.stem.split(".")[0]))
    return alpha, beta


def _run_main(tmp_path: Path, argv: list[str], monkeypatch) -> int:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    return main(argv)


def test_plan_dependents_reports_each_active_shared_test_lock_and_recovery_command(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands.plan import cmd_plan, cmd_plan_dependents
    from maid_runner.core.plan_lock import (
        PlanLockDependent,
        find_plan_lock_dependents,
    )

    alpha, beta = _write_shared_project(tmp_path)
    original_locks = {
        path.name: path.read_bytes()
        for path in sorted((tmp_path / ".maid" / "plan-locks").glob("*.json"))
    }
    (tmp_path / "tests" / "test_shared.py").write_text(
        "def test_shared_contract():\n    assert 1 + 2 == 3\n    assert 1 < 2\n",
        encoding="utf-8",
    )

    exit_code = _run_main(
        tmp_path,
        ["plan", "dependents", "tests/test_shared.py"],
        monkeypatch,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert callable(cmd_plan)
    assert callable(cmd_plan_dependents)
    assert PlanLockDependent.__name__ == "PlanLockDependent"
    assert "2 active plan locks pin 'tests/test_shared.py'" in output
    for manifest_path in (alpha, beta):
        slug = manifest_path.name.removesuffix(".manifest.yaml")
        assert f"{slug}: MISMATCH" in output
        assert f".maid/plan-locks/{slug}.lock.json" in output
        assert (
            f"maid plan revise manifests/{slug}.manifest.yaml "
            f'--reason "accept approved shared-test change" '
            "--preserve-red-evidence"
        ) in output
    assert {
        path.name: path.read_bytes()
        for path in sorted((tmp_path / ".maid" / "plan-locks").glob("*.json"))
    } == original_locks
    dependencies = find_plan_lock_dependents(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        "tests/test_shared.py",
    )
    assert all(isinstance(dependency, PlanLockDependent) for dependency in dependencies)
    assert [dependency.manifest_slug for dependency in dependencies] == [
        "alpha",
        "beta",
    ]
    assert [dependency.manifest_path for dependency in dependencies] == [
        "manifests/alpha.manifest.yaml",
        "manifests/beta.manifest.yaml",
    ]
    assert [dependency.lock_path for dependency in dependencies] == [
        ".maid/plan-locks/alpha.lock.json",
        ".maid/plan-locks/beta.lock.json",
    ]
    assert {dependency.test_path for dependency in dependencies} == {
        "tests/test_shared.py"
    }
    assert not any(dependency.test_hash_matches for dependency in dependencies)
    assert all(
        "--preserve-red-evidence" in dependency.recovery_command
        for dependency in dependencies
    )


def test_plan_dependents_json_excludes_superseded_locks(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_shared_project(tmp_path)
    replacement = tmp_path / "manifests" / "alpha-v2.manifest.yaml"
    replacement.write_text(
        _manifest_text(
            "alpha-v2",
            "src/alpha_v2.py",
            created="2026-08-09T00:02:00Z",
            supersedes="alpha",
        ),
        encoding="utf-8",
    )

    exit_code = _run_main(
        tmp_path,
        ["plan", "dependents", "tests/test_shared.py", "--json"],
        monkeypatch,
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["test_path"] == "tests/test_shared.py"
    assert payload["dependents"] == [
        {
            "manifest_slug": "beta",
            "manifest_path": "manifests/beta.manifest.yaml",
            "lock_path": ".maid/plan-locks/beta.lock.json",
            "test_path": "tests/test_shared.py",
            "test_hash_matches": True,
            "recovery_command": (
                "maid plan revise manifests/beta.manifest.yaml "
                '--reason "accept approved shared-test change" '
                "--preserve-red-evidence"
            ),
        }
    ]


def test_plan_dependents_rejects_out_of_project_paths(tmp_path: Path) -> None:
    from maid_runner.core.plan_lock import find_plan_lock_dependents

    _write_shared_project(tmp_path)
    chain = ManifestChain(tmp_path / "manifests", tmp_path)

    with pytest.raises(ValueError, match="outside project root"):
        find_plan_lock_dependents(chain, tmp_path, tmp_path.parent / "outside.py")


def test_plan_dependents_empty_query_succeeds_without_recovery_commands(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_shared_project(tmp_path)

    exit_code = _run_main(
        tmp_path,
        ["plan", "dependents", "tests/test_unlocked.py"],
        monkeypatch,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "0 active plan locks pin 'tests/test_unlocked.py'" in output
    assert "maid plan revise" not in output


def test_plan_dependents_recovery_command_preserves_non_default_project_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    project_root = tmp_path / "target project"
    project_root.mkdir()
    _write_shared_project(project_root)
    alpha_lock = project_root / ".maid" / "plan-locks" / "alpha.lock.json"
    alpha_payload = json.loads(alpha_lock.read_text(encoding="utf-8"))
    alpha_payload["red_evidence"] = {
        "red": True,
        "captured_at": "2026-08-09T00:00:00Z",
        "commands": [
            {
                "command": "python -m pytest -q tests/test_shared.py",
                "exit_code": 1,
                "output_tail": "1 failed",
                "classification": "red",
            }
        ],
    }
    alpha_lock.write_text(json.dumps(alpha_payload), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_main(
        tmp_path,
        [
            "plan",
            "dependents",
            "tests/test_shared.py",
            "--project-root",
            str(project_root),
        ],
        monkeypatch,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    expected_command = (
        f"maid plan revise '{project_root / 'manifests' / 'alpha.manifest.yaml'}' "
        f"--project-root '{project_root}' "
        '--reason "accept approved shared-test change" '
        "--preserve-red-evidence"
    )
    assert expected_command in output

    recovery_exit_code = _run_main(
        tmp_path,
        shlex.split(expected_command)[1:],
        monkeypatch,
    )

    assert recovery_exit_code == 0
    assert json.loads(alpha_lock.read_text(encoding="utf-8"))["revision"] == 2


def test_plan_dependents_fails_loudly_on_unreadable_active_lock(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_shared_project(tmp_path)
    (tmp_path / ".maid" / "plan-locks" / "alpha.lock.json").write_text(
        "{broken json",
        encoding="utf-8",
    )

    exit_code = _run_main(
        tmp_path,
        ["plan", "dependents", "tests/test_shared.py", "--json"],
        monkeypatch,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    error_payload = json.loads(captured.out)
    assert set(error_payload) == {"error"}
    assert "alpha.lock.json" in error_payload["error"]
    assert "cannot be loaded" in error_payload["error"]
    assert "dependents" not in error_payload
    assert captured.err == ""


def test_e701_suggests_querying_all_shared_test_dependents(tmp_path: Path) -> None:
    from maid_runner.core.plan_lock import enforce_plan_locks

    _write_shared_project(tmp_path)
    (tmp_path / "tests" / "test_shared.py").write_text(
        "def test_shared_contract():\n    assert 1 + 2 == 3\n    assert 1 < 2\n",
        encoding="utf-8",
    )

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    e701_errors = [
        error
        for error in errors
        if error.code is ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK
    ]
    assert len(e701_errors) == 2
    assert {error.suggestion for error in e701_errors} == {
        "Run `maid plan dependents tests/test_shared.py` to inspect every active "
        "lock that pins this behavioral test before revising evidence."
    }
