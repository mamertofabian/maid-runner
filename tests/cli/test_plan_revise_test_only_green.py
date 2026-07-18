"""Behavioral tests for --test-only-green plan-revise evidence mode."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import default_plan_lock_path, enforce_plan_locks
from maid_runner.core.result import ErrorCode


def _write_validate_script(tmp_path: Path, exit_code: int) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "validate.py").write_text(
        f"import sys\nprint('validate exit {exit_code}')\nsys.exit({exit_code})\n"
    )


def _manifest_text(
    *,
    goal: str = "Test-only contract",
    include_implementation: bool = False,
    extra_create: str = "",
    extra_scope: str = "",
) -> str:
    edit_block = """  edit:
    - path: tests/test_demo.py
      artifacts:
        - kind: test_function
          name: test_demo_contract
"""
    if include_implementation:
        edit_block += """    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
"""
    create_block = f"  create:\n{extra_create}" if extra_create else ""
    scope_block = f"  scope:\n{extra_scope}" if extra_scope else ""
    sections = [edit_block.rstrip()]
    if create_block:
        sections.append(create_block.rstrip())
    if scope_block:
        sections.append(scope_block.rstrip())
    files_body = "\n".join(sections)
    return f"""schema: "2"
goal: "{goal}"
type: feature
created: "2026-06-10T00:00:00Z"
files:
{files_body}
validate:
  - python scripts/validate.py
"""


def _write_test_only_project(
    tmp_path: Path,
    *,
    exit_code: int = 1,
    include_implementation: bool = False,
) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    if include_implementation:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "demo.py").write_text("def demo() -> int:\n    return 1\n")
    _write_validate_script(tmp_path, exit_code)
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        _manifest_text(include_implementation=include_implementation)
    )
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
        legacy_baseline=False,
        reason=None,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    reason: str,
    *,
    no_run: bool = False,
    preserve_red_evidence: bool = False,
    stash_implementation: bool = False,
    test_only_green: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=no_run,
        preserve_red_evidence=preserve_red_evidence,
        stash_implementation=stash_implementation,
        test_only_green=test_only_green,
        json=False,
    )


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "demo-task").read_text())


def _lock_test_only_project(
    tmp_path: Path, *, include_implementation: bool = False
) -> Path:
    manifest_path = _write_test_only_project(
        tmp_path, exit_code=1, include_implementation=include_implementation
    )
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    assert _lock_record(tmp_path)["red_evidence"]["red"] is True
    return manifest_path


def _revise_to_test_only_green(manifest_path: Path, tmp_path: Path) -> None:
    _write_validate_script(tmp_path, 0)
    manifest_path.write_text(_manifest_text(goal="Test-only contract after green"))
    assert (
        cmd_plan_revise(
            _revise_args(
                manifest_path,
                tmp_path,
                "test-only deliverable is green",
                test_only_green=True,
            )
        )
        == 0
    )
    evidence = _lock_record(tmp_path)["red_evidence"]
    assert evidence["red"] is False
    assert evidence["mode"] == "test_only_green"


def test_test_only_green_records_evidence_for_test_only_contract(
    tmp_path: Path,
) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    _revise_to_test_only_green(manifest_path, tmp_path)

    evidence = _lock_record(tmp_path)["red_evidence"]
    assert evidence["red"] is False
    assert evidence["mode"] == "test_only_green"
    assert evidence["captured_at"]
    assert len(evidence["commands"]) == 1
    command = evidence["commands"][0]
    assert command["command"] == "python scripts/validate.py"
    assert command["exit_code"] == 0
    assert command["classification"] == "not_red"


def test_test_only_green_refuses_manifest_with_implementation_file(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _lock_test_only_project(tmp_path, include_implementation=True)
    original = _lock_record(tmp_path)
    _write_validate_script(tmp_path, 0)
    manifest_path.write_text(
        _manifest_text(
            goal="Mixed contract after green",
            include_implementation=True,
        )
    )

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "should refuse mixed writable surface",
            test_only_green=True,
        )
    )

    assert exit_code == 2
    assert _lock_record(tmp_path) == original
    err = capsys.readouterr().err.lower()
    assert "--test-only-green" in err
    assert "stash-implementation" in err or "preserve-red-evidence" in err


def test_test_only_green_refuses_non_test_create_path(tmp_path: Path, capsys) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    original = _lock_record(tmp_path)
    _write_validate_script(tmp_path, 0)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "new_module.py").write_text(
        "def helper() -> int:\n    return 1\n"
    )
    manifest_path.write_text(
        _manifest_text(
            goal="Create bucket includes implementation",
            extra_create=(
                "    - path: src/new_module.py\n"
                "      artifacts:\n"
                "        - kind: function\n"
                "          name: helper\n"
            ),
        )
    )

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "should refuse non-test create path",
            test_only_green=True,
        )
    )

    assert exit_code == 2
    assert _lock_record(tmp_path) == original
    err = capsys.readouterr().err.lower()
    assert "--test-only-green" in err


def test_test_only_green_refuses_non_test_scope_path(tmp_path: Path, capsys) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    original = _lock_record(tmp_path)
    _write_validate_script(tmp_path, 0)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "wiring.py").write_text("WIRED = True\n")
    manifest_path.write_text(
        _manifest_text(
            goal="Scope bucket includes implementation",
            extra_scope="    - path: src/wiring.py\n      reason: wiring\n",
        )
    )

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "should refuse non-test scope path",
            test_only_green=True,
        )
    )

    assert exit_code == 2
    assert _lock_record(tmp_path) == original
    err = capsys.readouterr().err.lower()
    assert "--test-only-green" in err


def test_test_only_green_refuses_when_a_validate_command_fails(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    original = _lock_record(tmp_path)
    manifest_path.write_text(_manifest_text(goal="Still red test-only contract"))

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "validate still failing",
            test_only_green=True,
        )
    )

    assert exit_code != 0
    assert _lock_record(tmp_path) == original
    err = capsys.readouterr().err
    assert "validate exit 1" in err


def test_enforcement_accepts_test_only_green_within_bound(tmp_path: Path) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    _revise_to_test_only_green(manifest_path, tmp_path)

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    codes = {error.code for error in errors}
    assert ErrorCode.RED_PHASE_EVIDENCE_MISSING not in codes
    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID not in codes


def test_enforcement_rejects_test_only_green_after_contract_gains_implementation(
    tmp_path: Path,
) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    _revise_to_test_only_green(manifest_path, tmp_path)

    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    payload = json.loads(lock_path.read_text())
    payload["_manifest_contract"]["files"]["edit"].append("src/demo.py")
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    invalid = [
        error for error in errors if error.code == ErrorCode.RED_PHASE_EVIDENCE_INVALID
    ]
    assert invalid
    detail = " ".join(error.message for error in invalid).lower()
    assert "test_only_green" in detail or "test-only-green" in detail
    assert "contract" in detail or "mismatch" in detail


def test_enforcement_rejects_test_only_green_without_persisted_contract(
    tmp_path: Path,
) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    _revise_to_test_only_green(manifest_path, tmp_path)

    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    payload = json.loads(lock_path.read_text())
    del payload["_manifest_contract"]
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID in {error.code for error in errors}


def test_test_only_green_command_swap_still_fails_e707(tmp_path: Path) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    _revise_to_test_only_green(manifest_path, tmp_path)

    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"]["commands"][0]["command"] = "python scripts/other.py"
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH in {error.code for error in errors}


def test_test_only_green_flag_combinations_are_refused(tmp_path: Path, capsys) -> None:
    manifest_path = _lock_test_only_project(tmp_path)
    original = _lock_record(tmp_path)

    combinations = (
        {"stash_implementation": True},
        {"preserve_red_evidence": True},
        {"no_run": True},
    )
    for kwargs in combinations:
        exit_code = cmd_plan_revise(
            _revise_args(
                manifest_path,
                tmp_path,
                "mutual exclusion check",
                test_only_green=True,
                **kwargs,
            )
        )
        assert exit_code == 2
        assert _lock_record(tmp_path) == original
        err = capsys.readouterr().err.lower()
        assert "test-only-green" in err
        assert (
            "cannot be combined" in err
            or "mutually exclusive" in err
            or "cannot combine" in err
        )


def test_stash_refusal_names_test_only_green_path(tmp_path: Path, capsys) -> None:
    manifest_path = _lock_test_only_project(tmp_path)

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "stash on test-only contract",
            stash_implementation=True,
        )
    )

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "--test-only-green" in err
    assert "test-only" in err.lower()
