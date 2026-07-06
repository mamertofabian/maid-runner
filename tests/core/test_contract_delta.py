"""Behavioral tests for plan-lock contract delta evidence."""

from __future__ import annotations

import json
from pathlib import Path

from maid_runner.core import plan_lock
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
    revise_plan_lock,
)


def _contract(
    *,
    artifacts: tuple[str, ...] = (),
    files: dict[str, tuple[str, ...]] | None = None,
    validate_commands: tuple[str, ...] = (),
) -> dict:
    return {
        "artifacts": list(artifacts),
        "files": {section: list(paths) for section, paths in (files or {}).items()},
        "validate_commands": list(validate_commands),
    }


def _write_project(
    tmp_path: Path,
    *,
    extra_artifact: bool = False,
    validate_commands: tuple[str, ...] = ("python -m pytest -q tests/test_demo.py",),
) -> Path:
    (tmp_path / "manifests").mkdir(exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n\n"
        "def extra_demo() -> int:\n    return 2\n"
    )
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n    assert demo() == 1\n"
    )
    (tmp_path / "tests" / "test_extra.py").write_text(
        "from src.demo import extra_demo\n\n\n"
        "def test_extra_contract():\n    assert extra_demo() == 2\n"
    )
    (tmp_path / "docs" / "notes.md").write_text("notes\n")
    artifact_block = ""
    if extra_artifact:
        artifact_block = (
            "        - kind: function\n"
            "          name: extra_demo\n"
            "          returns: int\n"
        )
    validate_block = "\n".join(f"  - {command}" for command in validate_commands)
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Demo task"
type: feature
created: "2026-07-06T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          returns: int
{artifact_block}  read:
    - tests/test_demo.py
    - docs/notes.md
validate:
{validate_block}
"""
    )
    return manifest_path


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "demo-task").read_text())


def test_compute_contract_delta_reports_artifact_changes_sorted() -> None:
    delta = plan_lock.compute_contract_delta(
        _contract(artifacts=("src/demo.py:function:old", "src/z.py:function:z")),
        _contract(artifacts=("src/a.py:function:a", "src/z.py:function:z")),
    )

    assert delta.artifacts_added == ("src/a.py:function:a",)
    assert delta.artifacts_removed == ("src/demo.py:function:old",)


def test_compute_contract_delta_qualifies_file_changes_by_section() -> None:
    delta = plan_lock.compute_contract_delta(
        _contract(
            files={
                "create": ("src/demo.py",),
                "edit": ("tests/test_demo.py",),
                "read": ("docs/old.md",),
            }
        ),
        _contract(
            files={
                "create": ("src/generated.py",),
                "edit": ("src/demo.py",),
                "read": ("docs/new.md",),
            }
        ),
    )

    assert delta.files_added == (
        "create:src/generated.py",
        "edit:src/demo.py",
        "read:docs/new.md",
    )
    assert delta.files_removed == (
        "create:src/demo.py",
        "edit:tests/test_demo.py",
        "read:docs/old.md",
    )


def test_compute_contract_delta_reports_validate_command_changes() -> None:
    delta = plan_lock.compute_contract_delta(
        _contract(
            validate_commands=(
                "python -m pytest -q tests/test_old.py",
                "python -m pytest -q tests/test_shared.py",
            )
        ),
        _contract(
            validate_commands=(
                "python -m pytest -q tests/test_new.py",
                "python -m pytest -q tests/test_shared.py",
            )
        ),
    )

    assert delta.validate_commands_added == ("python -m pytest -q tests/test_new.py",)
    assert delta.validate_commands_removed == ("python -m pytest -q tests/test_old.py",)


def test_compute_contract_delta_identical_contracts_yield_empty_delta() -> None:
    contract = _contract(
        artifacts=("src/demo.py:function:demo",),
        files={"create": ("src/demo.py",), "read": ("tests/test_demo.py",)},
        validate_commands=("python -m pytest -q tests/test_demo.py",),
    )

    assert (
        plan_lock.compute_contract_delta(contract, contract)
        == plan_lock.ContractDelta()
    )


def test_revise_plan_lock_stores_delta_for_contract_change(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    original = create_plan_lock(manifest_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original.save(lock_path)
    prior_contract = _lock_record(tmp_path)["_manifest_contract"]
    manifest_path = _write_project(tmp_path, extra_artifact=True)

    revised = revise_plan_lock(
        original,
        manifest_path,
        tmp_path,
        "add test artifact",
        prior_contract=prior_contract,
    )

    delta = revised.revisions[0].contract_delta
    assert delta is not None
    assert "src/demo.py:function:extra_demo" in delta.artifacts_added
    assert delta.artifacts_removed == ()


def test_revise_plan_lock_stores_none_when_prior_contract_unavailable(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(tmp_path)
    original = create_plan_lock(manifest_path, tmp_path)

    revised = revise_plan_lock(
        original,
        manifest_path,
        tmp_path,
        "legacy lock without contract snapshot",
        prior_contract=None,
    )

    assert revised.revisions[0].contract_delta is None


def test_locks_with_and_without_deltas_verify_identically(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    original = create_plan_lock(manifest_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original.save(lock_path)
    prior_contract = _lock_record(tmp_path)["_manifest_contract"]
    revised = revise_plan_lock(
        original,
        manifest_path,
        tmp_path,
        "metadata-only relock",
        prior_contract=prior_contract,
    )
    revised.save(lock_path)

    with_delta_errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    payload = _lock_record(tmp_path)
    payload["revisions"][0].pop("contract_delta", None)
    lock_path.write_text(json.dumps(payload, indent=2))

    assert PlanLock.load(lock_path).revisions[0].contract_delta is None
    without_delta_errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    assert without_delta_errors == with_delta_errors == ()
