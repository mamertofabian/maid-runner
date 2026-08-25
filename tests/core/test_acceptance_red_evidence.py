"""Behavioral contract for acceptance-layer plan-lock red evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_revise
from maid_runner.core._file_discovery import is_test_file
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    capture_red_phase_evidence,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


def _write_script(tmp_path: Path, name: str, body: str) -> str:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    path = scripts / name
    path.write_text(body)
    return path.relative_to(tmp_path).as_posix()


def _write_project(
    tmp_path: Path,
    *,
    validate_command: str,
    acceptance_command: str,
) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "demo.py").write_text("def demo() -> int:\n    return 1\n")
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n"
        "    assert demo() == 1\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Demo task"
type: fix
created: "2026-08-25T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
  read:
    - tests/test_demo.py
validate:
  - {validate_command}
acceptance:
  tests:
    - {acceptance_command}
"""
    )
    return manifest_path


def _save_captured_lock(manifest_path: Path, project_root: Path) -> Path:
    evidence = capture_red_phase_evidence(manifest_path, project_root).to_payload()
    lock = replace(
        create_plan_lock(manifest_path, project_root),
        red_evidence=evidence,
    )
    lock_path = default_plan_lock_path(project_root, "demo-task")
    lock.save(lock_path)
    return lock_path


def _enforce(project_root: Path):
    return enforce_plan_locks(
        ManifestChain(project_root / "manifests", project_root),
        project_root,
        require_plan_lock=True,
        require_red_evidence=True,
    )


def _preserve_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="preserve unchanged acceptance evidence",
        no_run=False,
        preserve_red_evidence=True,
        stash_implementation=False,
        allow_sibling_dirty=False,
        test_only_green=False,
        json=False,
    )


def test_capture_uses_acceptance_red_when_validate_commands_are_green(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "print('fast gate passed')\n")
    red = _write_script(
        tmp_path,
        "acceptance_red.py",
        "print('browser assertion failed')\nimport sys\nsys.exit(1)\n",
    )
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )

    evidence = capture_red_phase_evidence(manifest_path, tmp_path)

    assert evidence.red is True
    assert evidence.command_source == "validate_and_acceptance"
    assert evidence.to_payload()["command_source"] == "validate_and_acceptance"
    assert [command.classification for command in evidence.commands] == [
        "not_red",
        "red",
    ]


def test_capture_skips_acceptance_when_validate_already_has_red(
    tmp_path: Path,
) -> None:
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    marker = tmp_path / "acceptance-ran"
    acceptance = _write_script(
        tmp_path,
        "acceptance.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
    )
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {red}",
        acceptance_command=f"python {acceptance}",
    )

    evidence = capture_red_phase_evidence(manifest_path, tmp_path)

    assert evidence.red is True
    assert "command_source" not in evidence.to_payload()
    assert len(evidence.commands) == 1
    assert not marker.exists()


def test_capture_does_not_mask_invalid_validate_with_acceptance_red(
    tmp_path: Path,
) -> None:
    invalid = _write_script(tmp_path, "invalid.py", "import sys\nsys.exit(2)\n")
    marker = tmp_path / "acceptance-ran"
    acceptance = _write_script(
        tmp_path,
        "acceptance.py",
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n"
        "import sys\nsys.exit(1)\n",
    )
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {invalid}",
        acceptance_command=f"python {acceptance}",
    )

    evidence = capture_red_phase_evidence(manifest_path, tmp_path)

    assert evidence.red is False
    assert evidence.commands[0].classification == "invalid"
    assert not marker.exists()


def test_acceptance_red_evidence_passes_e707_command_integrity(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    _save_captured_lock(manifest_path, tmp_path)

    errors = _enforce(tmp_path)

    assert errors == ()


def test_acceptance_red_evidence_missing_acceptance_command_fails_e707(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"]["commands"] = payload["red_evidence"]["commands"][:1]
    lock_path.write_text(json.dumps(payload))

    errors = _enforce(tmp_path)

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH in {error.code for error in errors}


def test_acceptance_red_evidence_cross_layer_swap_fails_e707(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    contract = payload["_manifest_contract"]
    contract["validate_commands"], contract["acceptance_commands"] = (
        contract["acceptance_commands"],
        contract["validate_commands"],
    )
    lock_path.write_text(json.dumps(payload))

    errors = _enforce(tmp_path)

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH in {error.code for error in errors}


def test_acceptance_red_evidence_without_acceptance_snapshot_fails_e707(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["_manifest_contract"].pop("acceptance_commands")
    lock_path.write_text(json.dumps(payload))

    errors = _enforce(tmp_path)

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH in {error.code for error in errors}


def test_acceptance_red_evidence_without_contract_snapshot_fails_e707(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload.pop("_manifest_contract")
    lock_path.write_text(json.dumps(payload))

    errors = _enforce(tmp_path)

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH in {error.code for error in errors}


def test_acceptance_red_evidence_with_unknown_command_source_fails_e707(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"]["command_source"] = "unknown_source"
    payload["red_evidence"]["commands"][0]["command"] = "python spliced.py"
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths=(),
    )

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH in {error.code for error in errors}


def test_legacy_validate_only_evidence_remains_valid_with_acceptance_contract(
    tmp_path: Path,
) -> None:
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    acceptance = _write_script(tmp_path, "acceptance.py", "pass\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {red}",
        acceptance_command=f"python {acceptance}",
    )
    _save_captured_lock(manifest_path, tmp_path)

    errors = _enforce(tmp_path)

    assert errors == ()


def test_legacy_validate_only_evidence_without_contract_snapshot_remains_valid(
    tmp_path: Path,
) -> None:
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    acceptance = _write_script(tmp_path, "acceptance.py", "pass\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {red}",
        acceptance_command=f"python {acceptance}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload.pop("_manifest_contract")
    lock_path.write_text(json.dumps(payload))

    errors = _enforce(tmp_path)

    assert errors == ()


def test_capture_runs_all_acceptance_commands_and_rejects_invalid_exit(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    invalid = _write_script(tmp_path, "invalid.py", "import sys\nsys.exit(2)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    manifest_path.write_text(
        manifest_path.read_text().replace(
            f"    - python {red}\n",
            f"    - python {red}\n    - python {invalid}\n",
        )
    )

    evidence = capture_red_phase_evidence(manifest_path, tmp_path)

    assert evidence.red is False
    assert [command.classification for command in evidence.commands] == [
        "not_red",
        "red",
        "invalid",
    ]


def test_preserve_acceptance_red_evidence_accepts_unchanged_commands(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    original_evidence = json.loads(lock_path.read_text())["red_evidence"]

    exit_code = cmd_plan_revise(_preserve_args(manifest_path, tmp_path))

    revised = json.loads(lock_path.read_text())
    assert exit_code == 0
    assert revised["revision"] == 2
    assert revised["red_evidence"] == original_evidence


def test_preserve_acceptance_red_evidence_rejects_changed_acceptance_commands(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    changed = _write_script(tmp_path, "changed.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    original_lock = lock_path.read_bytes()
    manifest_path.write_text(
        manifest_path.read_text().replace(f"python {red}", f"python {changed}")
    )

    exit_code = cmd_plan_revise(_preserve_args(manifest_path, tmp_path))

    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock


def test_preserve_acceptance_red_evidence_rejects_cross_layer_swap(
    tmp_path: Path,
) -> None:
    green = _write_script(tmp_path, "green.py", "pass\n")
    red = _write_script(tmp_path, "red.py", "import sys\nsys.exit(1)\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {green}",
        acceptance_command=f"python {red}",
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    original_lock = lock_path.read_bytes()
    manifest_path.write_text(
        manifest_path.read_text()
        .replace(f"  - python {green}\n", f"  - python {red}\n")
        .replace(f"    - python {red}\n", f"    - python {green}\n")
    )

    exit_code = cmd_plan_revise(_preserve_args(manifest_path, tmp_path))

    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock


def test_preserve_acceptance_red_evidence_accepts_reordering_within_layers(
    tmp_path: Path,
) -> None:
    validate_a = _write_script(tmp_path, "validate_a.py", "pass\n")
    validate_b = _write_script(tmp_path, "validate_b.py", "pass\n")
    acceptance_a = _write_script(
        tmp_path, "acceptance_a.py", "import sys\nsys.exit(1)\n"
    )
    acceptance_b = _write_script(tmp_path, "acceptance_b.py", "pass\n")
    manifest_path = _write_project(
        tmp_path,
        validate_command=f"python {validate_a}",
        acceptance_command=f"python {acceptance_a}",
    )
    manifest_path.write_text(
        manifest_path.read_text()
        .replace(
            f"  - python {validate_a}\n",
            f"  - python {validate_a}\n  - python {validate_b}\n",
        )
        .replace(
            f"    - python {acceptance_a}\n",
            f"    - python {acceptance_a}\n    - python {acceptance_b}\n",
        )
    )
    lock_path = _save_captured_lock(manifest_path, tmp_path)
    original_evidence = json.loads(lock_path.read_text())["red_evidence"]
    manifest_path.write_text(
        manifest_path.read_text()
        .replace(
            f"  - python {validate_a}\n  - python {validate_b}\n",
            f"  - python {validate_b}\n  - python {validate_a}\n",
        )
        .replace(
            f"    - python {acceptance_a}\n    - python {acceptance_b}\n",
            f"    - python {acceptance_b}\n    - python {acceptance_a}\n",
        )
    )

    exit_code = cmd_plan_revise(_preserve_args(manifest_path, tmp_path))

    revised = json.loads(lock_path.read_text())
    assert exit_code == 0
    assert revised["red_evidence"] == original_evidence


def test_cypress_suffixes_are_test_files() -> None:
    assert is_test_file("route-plan.cy.ts") is True
    assert is_test_file("route-plan.cy.tsx") is True
    assert is_test_file("route-plan.cy.js") is True
    assert is_test_file("route-plan.cy.jsx") is True
    assert is_test_file("route-plan.ts") is False
