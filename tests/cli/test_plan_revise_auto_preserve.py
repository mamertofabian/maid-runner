"""Behavioral tests for automatic red-evidence preservation on plain revise."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


def _write_project(tmp_path: Path, exit_code: int = 1) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    (tmp_path / "scripts" / "validate.py").write_text(
        f"import sys\nprint('validate exit {exit_code}')\nsys.exit({exit_code})\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(_manifest_text())
    return manifest_path


def _manifest_text(
    *,
    goal: str = "Demo task",
    validate_extra: str = "",
    read_line: str = "    - tests/test_demo.py\n",
) -> str:
    return f"""schema: "2"
goal: "{goal}"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
  read:
{read_line}validate:
  - python scripts/validate.py
{validate_extra}"""


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
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=no_run,
        preserve_red_evidence=preserve_red_evidence,
        stash_implementation=stash_implementation,
        json=False,
    )


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "demo-task").read_text())


def _lock_with_red_evidence(
    tmp_path: Path, *, read_line: str = "    - tests/test_demo.py\n"
) -> tuple[Path, dict]:
    manifest_path = _write_project(tmp_path, exit_code=1)
    if read_line != "    - tests/test_demo.py\n":
        manifest_path.write_text(_manifest_text(read_line=read_line))
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    record = _lock_record(tmp_path)
    assert record["red_evidence"]["red"] is True
    return manifest_path, record


def _outcome_style_manifest_edit(
    manifest_path: Path, *, read_line: str = "    - tests/test_demo.py\n"
) -> None:
    manifest_path.write_text(
        _manifest_text(
            goal="Demo task after outcome capture",
            read_line=read_line,
        )
    )


def test_revise_manifest_only_edit_preserves_red_evidence(
    tmp_path: Path, capsys
) -> None:
    manifest_path, original = _lock_with_red_evidence(tmp_path)
    original_evidence = original["red_evidence"]
    (tmp_path / "scripts" / "validate.py").write_text(
        "import sys\nprint('validate exit 0')\nsys.exit(0)\n"
    )
    _outcome_style_manifest_edit(manifest_path)

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "refresh after outcome capture")
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"] == original_evidence
    delta = record["revisions"][0]["contract_delta"]
    assert delta == {
        "artifacts_added": [],
        "artifacts_removed": [],
        "files_added": [],
        "files_removed": [],
        "validate_commands_added": [],
        "validate_commands_removed": [],
    }
    captured = capsys.readouterr().out
    assert "red evidence" in captured.lower()
    assert "preserved" in captured.lower()
    assert "contract-preserving" in captured.lower()


def test_revise_with_changed_test_file_recaptures_evidence(tmp_path: Path) -> None:
    manifest_path, original = _lock_with_red_evidence(tmp_path)
    original_evidence = original["red_evidence"]
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert False\n"
    )

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "assertion change forced recapture")
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"] != original_evidence
    assert record["red_evidence"]["commands"][0]["classification"] == "red"


def test_revise_with_formatter_only_test_edit_preserves_red_evidence(
    tmp_path: Path, capsys
) -> None:
    manifest_path, original = _lock_with_red_evidence(tmp_path)
    original_evidence = original["red_evidence"]
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True  # formatting churn\n"
    )

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "formatter-only test edit")
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"] == original_evidence
    captured = capsys.readouterr().out
    assert "preserved" in captured.lower()
    assert "contract-preserving" in captured.lower()


def test_revise_with_new_discovered_test_file_recaptures_evidence(
    tmp_path: Path,
) -> None:
    directory_read = "    - tests/\n"
    manifest_path, original = _lock_with_red_evidence(
        tmp_path, read_line=directory_read
    )
    original_evidence = original["red_evidence"]
    assert "tests/test_demo.py" in original["test_hashes"]
    assert "tests/test_extra.py" not in original["test_hashes"]
    (tmp_path / "tests" / "test_extra.py").write_text(
        "def test_extra_contract():\n    assert True\n"
    )
    (tmp_path / "scripts" / "validate.py").write_text(
        "import sys\nprint('validate exit 0')\nsys.exit(0)\n"
    )
    _outcome_style_manifest_edit(manifest_path, read_line=directory_read)

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "discovery grew a new test file")
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"] != original_evidence
    assert record["red_evidence"]["red"] is False
    assert "tests/test_extra.py" in record["test_hashes"]


def test_revise_with_contract_delta_recaptures_evidence(tmp_path: Path) -> None:
    manifest_path, original = _lock_with_red_evidence(tmp_path)
    original_evidence = original["red_evidence"]
    manifest_path.write_text(
        _manifest_text(validate_extra="  - python scripts/extra_validate.py\n")
    )
    (tmp_path / "scripts" / "extra_validate.py").write_text(
        "import sys\nprint('extra')\nsys.exit(1)\n"
    )

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "add validate command")
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"] != original_evidence
    delta = record["revisions"][0]["contract_delta"]
    assert delta["validate_commands_added"] == ["python scripts/extra_validate.py"]


def test_revise_with_invalid_existing_evidence_recaptures(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path, exit_code=0)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    original = _lock_record(tmp_path)
    assert original["red_evidence"]["red"] is False
    _outcome_style_manifest_edit(manifest_path)
    (tmp_path / "scripts" / "validate.py").write_text(
        "import sys\nprint('validate exit 1')\nsys.exit(1)\n"
    )

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "plain revise after green lock")
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"] != original["red_evidence"]
    assert record["red_evidence"]["red"] is True


def test_revision_preserves_red_evidence_predicate(tmp_path: Path) -> None:
    from maid_runner.core import plan_lock as plan_lock_module

    assert hasattr(plan_lock_module, "revision_preserves_red_evidence")
    revision_preserves_red_evidence = plan_lock_module.revision_preserves_red_evidence

    manifest_path, _ = _lock_with_red_evidence(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    existing = PlanLock.load(lock_path)
    prior_contract = _lock_record(tmp_path)["_manifest_contract"]

    assert (
        revision_preserves_red_evidence(
            existing, manifest_path, tmp_path, prior_contract
        )
        is True
    )

    _outcome_style_manifest_edit(manifest_path)
    assert (
        revision_preserves_red_evidence(
            existing, manifest_path, tmp_path, prior_contract
        )
        is True
    )

    assert (
        revision_preserves_red_evidence(existing, manifest_path, tmp_path, None)
        is False
    )

    Path(manifest_path).write_text(
        _manifest_text(validate_extra="  - python scripts/extra_validate.py\n")
    )
    assert (
        revision_preserves_red_evidence(
            existing, manifest_path, tmp_path, prior_contract
        )
        is False
    )
    _outcome_style_manifest_edit(manifest_path)

    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert False\n"
    )
    assert (
        revision_preserves_red_evidence(
            existing, manifest_path, tmp_path, prior_contract
        )
        is False
    )
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )

    directory_manifest = tmp_path / "manifests" / "demo-dir.manifest.yaml"
    directory_manifest.write_text(_manifest_text(read_line="    - tests/\n"))
    assert cmd_plan_lock(_lock_args(directory_manifest, tmp_path)) == 0
    dir_lock = PlanLock.load(default_plan_lock_path(tmp_path, "demo-dir"))
    dir_prior = json.loads(default_plan_lock_path(tmp_path, "demo-dir").read_text())[
        "_manifest_contract"
    ]
    (tmp_path / "tests" / "test_extra.py").write_text(
        "def test_extra_contract():\n    assert True\n"
    )
    assert (
        revision_preserves_red_evidence(
            dir_lock, directory_manifest, tmp_path, dir_prior
        )
        is False
    )
    (tmp_path / "tests" / "test_extra.py").unlink()

    green_lock = replace(
        existing,
        red_evidence={
            "red": False,
            "captured_at": "2026-07-18T00:00:00+00:00",
            "commands": [
                {
                    "command": "python scripts/validate.py",
                    "exit_code": 0,
                    "output_tail": "ok",
                    "classification": "not_red",
                }
            ],
        },
    )
    assert (
        revision_preserves_red_evidence(
            green_lock, manifest_path, tmp_path, prior_contract
        )
        is False
    )


def test_preserved_evidence_passes_verify_red_evidence_gate(tmp_path: Path) -> None:
    manifest_path, _ = _lock_with_red_evidence(tmp_path)
    (tmp_path / "scripts" / "validate.py").write_text(
        "import sys\nprint('validate exit 0')\nsys.exit(0)\n"
    )
    _outcome_style_manifest_edit(manifest_path)
    assert (
        cmd_plan_revise(
            _revise_args(manifest_path, tmp_path, "refresh after outcome capture")
        )
        == 0
    )

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_PHASE_EVIDENCE_MISSING not in {error.code for error in errors}
    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID not in {error.code for error in errors}
