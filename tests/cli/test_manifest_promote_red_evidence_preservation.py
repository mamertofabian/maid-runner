"""Regression tests for preserving valid red evidence during promotion."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import yaml

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.core.plan_lock import (
    PlanLock,
    capture_red_phase_evidence,
    create_plan_lock,
    default_plan_lock_path,
    revision_preserves_red_evidence,
)


DRAFT_NAME = "activate-contract.manifest.yaml"
SLUG = "activate-contract"


def _write_draft(project_root: Path, validate_commands: list[str]) -> Path:
    draft_path = project_root / "manifests" / "drafts" / DRAFT_NAME
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Activate an existing contract",
                "type": "fix",
                "created": "2026-08-15",
                "files": {
                    "create": [
                        {
                            "path": "src/example.py",
                            "artifacts": [{"kind": "function", "name": "example_func"}],
                        }
                    ]
                },
                "validate": validate_commands,
            },
            sort_keys=False,
        )
    )
    return draft_path


def _write_test_only_draft(project_root: Path) -> tuple[Path, Path]:
    test_path = project_root / "tests" / "test_contract.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text("def test_contract():\n    assert True\n")
    draft_path = project_root / "manifests" / "drafts" / DRAFT_NAME
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Strengthen a behavioral contract",
                "type": "fix",
                "created": "2026-08-15",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_contract.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_contract"}
                            ],
                        }
                    ]
                },
                "validate": ["pytest -q tests/test_contract.py"],
            },
            sort_keys=False,
        )
    )
    return draft_path, test_path


def _lock_with_red_evidence(project_root: Path, draft_path: Path) -> Path:
    lock = create_plan_lock(draft_path, project_root)
    lock = replace(
        lock,
        red_evidence=capture_red_phase_evidence(draft_path, project_root).to_payload(),
    )
    lock_path = default_plan_lock_path(project_root, SLUG)
    lock.save(lock_path)
    return lock_path


def _promote(project_root: Path, draft_path: Path, *, no_run: bool = False) -> int:
    return cmd_manifest(
        argparse.Namespace(
            manifest_command="promote",
            manifest_path=str(draft_path),
            output_dir=str(project_root / "manifests"),
            project_root=str(project_root),
            no_run=no_run,
            json=False,
        )
    )


def _activation_command() -> str:
    return (
        'python -c "from pathlib import Path; '
        "raise SystemExit(0 if "
        "Path('manifests/activate-contract.manifest.yaml').exists() else 1)\""
    )


def test_promote_preserves_valid_red_evidence_when_activation_turns_green(
    tmp_path,
):
    draft_path = _write_draft(tmp_path, [_activation_command()])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    before = PlanLock.load(lock_path).red_evidence

    assert before is not None
    assert before["red"] is True
    assert _promote(tmp_path, draft_path) == 0

    after = PlanLock.load(lock_path).red_evidence
    assert after == before
    assert after["commands"][0]["exit_code"] == 1


def test_promote_no_run_preserves_valid_red_evidence(tmp_path):
    draft_path = _write_draft(tmp_path, [_activation_command()])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    before = PlanLock.load(lock_path).red_evidence

    assert before is not None
    assert before["red"] is True
    assert _promote(tmp_path, draft_path, no_run=True) == 0

    assert PlanLock.load(lock_path).red_evidence == before


def test_promote_recaptures_when_locked_validate_commands_changed(tmp_path):
    first_command = "python -c \"print('ORIGINAL_RED'); raise SystemExit(1)\""
    second_command = "python -c \"print('RECAPTURED_RED'); raise SystemExit(1)\""
    draft_path = _write_draft(tmp_path, [first_command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    before = PlanLock.load(lock_path).red_evidence
    draft_path = _write_draft(tmp_path, [second_command])

    assert before is not None
    assert _promote(tmp_path, draft_path) == 0

    after = PlanLock.load(lock_path).red_evidence
    assert after is not None
    assert after != before
    assert after["red"] is True
    assert "RECAPTURED_RED" in after["commands"][0]["command"]
    assert "RECAPTURED_RED" in after["commands"][0]["output_tail"]


def test_promote_no_run_clears_evidence_when_locked_tests_changed(tmp_path):
    test_path = tmp_path / "tests" / "test_contract.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_contract():\n    assert False\n")
    command = "pytest -q tests/test_contract.py"
    draft_path = _write_draft(tmp_path, [command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    test_path.write_text("def test_contract():\n    assert False, 'changed contract'\n")

    assert _promote(tmp_path, draft_path, no_run=True) == 0

    assert PlanLock.load(lock_path).red_evidence is None


def test_promote_recaptures_when_self_referencing_validate_path_is_rewritten(
    tmp_path,
):
    old_path = f"manifests/drafts/{DRAFT_NAME}"
    new_path = f"manifests/{DRAFT_NAME}"
    command = f'python -c "raise SystemExit(1)" {old_path}'
    draft_path = _write_draft(tmp_path, [command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    before = PlanLock.load(lock_path).red_evidence

    assert before is not None
    assert old_path in before["commands"][0]["command"]
    assert _promote(tmp_path, draft_path) == 0

    after = PlanLock.load(lock_path).red_evidence
    assert after is not None
    assert after != before
    assert after["red"] is True
    assert new_path in after["commands"][0]["command"]
    assert old_path not in after["commands"][0]["command"]


def test_revision_preservation_rejects_inconsistent_red_command_payload(tmp_path):
    command = 'python -c "raise SystemExit(1)"'
    draft_path = _write_draft(tmp_path, [command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    lock = PlanLock.load(lock_path)
    prior_contract = json.loads(lock_path.read_text())["_manifest_contract"]
    for forged_exit_code in (0, True):
        forged = replace(
            lock,
            red_evidence={
                "red": True,
                "captured_at": "2026-08-15T00:00:00+00:00",
                "commands": [
                    {
                        "command": prior_contract["validate_commands"][0],
                        "exit_code": forged_exit_code,
                        "output_tail": "never executed",
                        "classification": "red",
                    }
                ],
            },
        )

        assert (
            revision_preserves_red_evidence(
                forged,
                draft_path,
                tmp_path,
                prior_contract,
            )
            is False
        )


def test_promote_does_not_preserve_inconsistent_red_command_payload(tmp_path):
    command = 'python -c "raise SystemExit(1)"'
    draft_path = _write_draft(tmp_path, [command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    lock = PlanLock.load(lock_path)
    prior_contract = json.loads(lock_path.read_text())["_manifest_contract"]
    forged = {
        "red": True,
        "captured_at": "2026-08-15T00:00:00+00:00",
        "commands": [
            {
                "command": prior_contract["validate_commands"][0],
                "exit_code": True,
                "output_tail": "never executed",
                "classification": "red",
            }
        ],
    }
    replace(lock, red_evidence=forged).save(lock_path)

    assert _promote(tmp_path, draft_path, no_run=True) == 0

    assert PlanLock.load(lock_path).red_evidence is None


def test_promote_does_not_preserve_command_spliced_red_evidence(tmp_path):
    command = 'python -c "raise SystemExit(1)"'
    draft_path = _write_draft(tmp_path, [command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    lock = PlanLock.load(lock_path)
    forged = {
        **lock.red_evidence,
        "commands": [
            {
                **lock.red_evidence["commands"][0],
                "command": "python -c \"print('spliced'); raise SystemExit(1)\"",
            }
        ],
    }
    replace(lock, red_evidence=forged).save(lock_path)

    assert _promote(tmp_path, draft_path, no_run=True) == 0

    assert PlanLock.load(lock_path).red_evidence is None


def test_revision_preservation_rejects_contradictory_evidence_mode(tmp_path):
    command = 'python -c "raise SystemExit(1)"'
    draft_path = _write_draft(tmp_path, [command])
    lock_path = _lock_with_red_evidence(tmp_path, draft_path)
    lock = PlanLock.load(lock_path)
    prior_contract = json.loads(lock_path.read_text())["_manifest_contract"]
    contradictory = replace(
        lock,
        red_evidence={
            **lock.red_evidence,
            "mode": "test_only_green",
        },
    )

    assert (
        revision_preserves_red_evidence(
            contradictory,
            draft_path,
            tmp_path,
            prior_contract,
        )
        is False
    )


def test_revision_preservation_requires_consistent_test_only_commands(tmp_path):
    draft_path, _ = _write_test_only_draft(tmp_path)
    lock = create_plan_lock(draft_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, SLUG)
    lock.save(lock_path)
    prior_contract = json.loads(lock_path.read_text())["_manifest_contract"]
    valid_command = {
        "command": prior_contract["validate_commands"][0],
        "exit_code": 0,
        "output_tail": "1 passed",
        "classification": "not_red",
    }
    valid_evidence = {
        "red": False,
        "mode": "test_only_green",
        "captured_at": "2026-08-15T00:00:00+00:00",
        "commands": [valid_command],
    }

    assert revision_preserves_red_evidence(
        replace(lock, red_evidence=valid_evidence),
        draft_path,
        tmp_path,
        prior_contract,
    )

    for invalid_command in (
        {**valid_command, "exit_code": False},
        {key: value for key, value in valid_command.items() if key != "output_tail"},
    ):
        invalid_evidence = {**valid_evidence, "commands": [invalid_command]}
        assert (
            revision_preserves_red_evidence(
                replace(lock, red_evidence=invalid_evidence),
                draft_path,
                tmp_path,
                prior_contract,
            )
            is False
        )


def test_revision_preservation_rejects_spliced_special_mode_commands(tmp_path):
    commands = [
        'python -c "raise SystemExit(1)"',
        'python -c "raise SystemExit(2)"',
    ]
    draft_path = _write_draft(tmp_path, commands)
    lock = create_plan_lock(draft_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, SLUG)
    lock.save(lock_path)
    prior_contract = json.loads(lock_path.read_text())["_manifest_contract"]
    spliced_commands = [
        {
            "command": "python -c \"print('spliced red'); raise SystemExit(1)\"",
            "exit_code": 1,
            "output_tail": "red",
            "classification": "red",
        },
        {
            "command": prior_contract["validate_commands"][1],
            "exit_code": 2,
            "output_tail": "invalid",
            "classification": "invalid",
        },
    ]
    restored_commands = [
        {**spliced_commands[0], "output_tail": "restored red"},
        {
            **spliced_commands[1],
            "exit_code": 1,
            "output_tail": "restored red",
            "classification": "red",
        },
    ]
    stash_evidence = {
        "red": True,
        "mode": "stash_restoration",
        "captured_at": "2026-08-15T00:00:00+00:00",
        "restored_captured_at": "2026-08-15T00:00:01+00:00",
        "commands": spliced_commands,
        "restored_commands": restored_commands,
    }

    assert (
        revision_preserves_red_evidence(
            replace(lock, red_evidence=stash_evidence),
            draft_path,
            tmp_path,
            prior_contract,
        )
        is False
    )

    test_only_path, _ = _write_test_only_draft(tmp_path)
    test_only_lock = create_plan_lock(test_only_path, tmp_path)
    test_only_lock_path = default_plan_lock_path(tmp_path, SLUG)
    test_only_lock.save(test_only_lock_path)
    test_only_contract = json.loads(test_only_lock_path.read_text())[
        "_manifest_contract"
    ]
    test_only_evidence = {
        "red": False,
        "mode": "test_only_green",
        "captured_at": "2026-08-15T00:00:00+00:00",
        "commands": [
            {
                "command": "pytest -q tests/test_spliced.py",
                "exit_code": 0,
                "output_tail": "1 passed",
                "classification": "not_red",
            }
        ],
    }

    assert (
        revision_preserves_red_evidence(
            replace(test_only_lock, red_evidence=test_only_evidence),
            test_only_path,
            tmp_path,
            test_only_contract,
        )
        is False
    )


def test_promote_preserves_consistent_test_only_evidence(tmp_path):
    draft_path, _ = _write_test_only_draft(tmp_path)
    lock = create_plan_lock(draft_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, SLUG)
    lock.save(lock_path)
    prior_contract = json.loads(lock_path.read_text())["_manifest_contract"]
    evidence = {
        "red": False,
        "mode": "test_only_green",
        "captured_at": "2026-08-15T00:00:00+00:00",
        "commands": [
            {
                "command": prior_contract["validate_commands"][0],
                "exit_code": 0,
                "output_tail": "1 passed",
                "classification": "not_red",
            }
        ],
    }
    replace(lock, red_evidence=evidence).save(lock_path)

    assert _promote(tmp_path, draft_path, no_run=True) == 0

    assert PlanLock.load(lock_path).red_evidence == evidence


def test_promotion_docs_describe_valid_evidence_preservation():
    project_root = Path(__file__).resolve().parents[2]
    workflow = (project_root / "docs" / "draft-manifest-workflow.md").read_text()
    packaged_workflow = (
        project_root / "maid_runner" / "docs" / "draft-manifest-workflow.md"
    ).read_text()

    assert "preserves valid red-phase evidence" in workflow
    assert "recaptures evidence when the locked contract or tests changed" in workflow
    assert "--no-run" in workflow
    assert packaged_workflow == workflow
