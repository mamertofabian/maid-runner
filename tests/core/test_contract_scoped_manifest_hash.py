"""Behavioral tests for contract-scoped plan-lock manifest hashing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from maid_runner.cli.commands.plan import cmd_plan_status
from maid_runner.core import plan_lock as plan_lock_mod
from maid_runner.core.plan_lock import create_plan_lock
from maid_runner.core.supersession_audit import compute_manifest_hash


_BASELINE_MANIFEST = """\
schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-10T00:00:00Z"
description: |
  Baseline description for contract hashing.
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""


_OUTCOME_SECTION = """\
outcome:
  status: completed
  summary: "Outcome capture must not change the contract hash."
  completed: "2026-07-18T00:00:00Z"
  validation:
    - command: "uv run python -m pytest -q"
      result: passed
  review:
    verdict: ready
    findings: []
  lessons: []
"""


def _compute_manifest_contract_hash(manifest_path: Path) -> str:
    assert hasattr(
        plan_lock_mod, "compute_manifest_contract_hash"
    ), "compute_manifest_contract_hash must be public on plan_lock"
    return plan_lock_mod.compute_manifest_contract_hash(manifest_path)


def _manifest_hash_matches(lock_hash: str, manifest_path: Path) -> bool:
    assert hasattr(
        plan_lock_mod, "manifest_hash_matches"
    ), "manifest_hash_matches must be public on plan_lock"
    return plan_lock_mod.manifest_hash_matches(lock_hash, manifest_path)


def _write_project(tmp_path: Path, text: str = _BASELINE_MANIFEST) -> Path:
    (tmp_path / "manifests").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo():\n    assert True\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(text, encoding="utf-8")
    return manifest_path


def _status_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="status",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=True,
    )


def test_contract_hash_ignores_outcome_section(tmp_path: Path) -> None:
    baseline = _write_project(tmp_path)
    with_outcome = tmp_path / "manifests" / "with-outcome.manifest.yaml"
    with_outcome.write_text(_BASELINE_MANIFEST + _OUTCOME_SECTION, encoding="utf-8")

    assert _compute_manifest_contract_hash(baseline) == _compute_manifest_contract_hash(
        with_outcome
    )
    assert _compute_manifest_contract_hash(baseline).startswith("sha256-contract:")


def test_contract_hash_tracks_contract_changes(tmp_path: Path) -> None:
    baseline = _write_project(tmp_path)
    baseline_hash = _compute_manifest_contract_hash(baseline)

    artifact_changed = tmp_path / "manifests" / "artifact-changed.manifest.yaml"
    artifact_changed.write_text(
        _BASELINE_MANIFEST.replace("name: demo", "name: demo_renamed"),
        encoding="utf-8",
    )
    files_changed = tmp_path / "manifests" / "files-changed.manifest.yaml"
    files_changed.write_text(
        _BASELINE_MANIFEST.replace("path: src/demo.py", "path: src/demo_renamed.py"),
        encoding="utf-8",
    )
    validate_changed = tmp_path / "manifests" / "validate-changed.manifest.yaml"
    validate_changed.write_text(
        _BASELINE_MANIFEST.replace(
            "python -m pytest -q tests/test_demo.py",
            "python -m pytest -q tests/test_demo.py -k demo",
        ),
        encoding="utf-8",
    )
    description_changed = tmp_path / "manifests" / "description-changed.manifest.yaml"
    description_changed.write_text(
        _BASELINE_MANIFEST.replace(
            "Baseline description for contract hashing.",
            "Description-only edit must still change the contract hash.",
        ),
        encoding="utf-8",
    )

    for variant in (
        artifact_changed,
        files_changed,
        validate_changed,
        description_changed,
    ):
        assert _compute_manifest_contract_hash(variant) != baseline_hash


def test_contract_hash_ignores_yaml_formatting_only_edits(tmp_path: Path) -> None:
    baseline = _write_project(tmp_path)
    data = yaml.safe_load(baseline.read_text(encoding="utf-8"))
    reformatted = tmp_path / "manifests" / "reformatted.manifest.yaml"
    reformatted.write_text(
        "# formatting-only comment\n"
        + yaml.dump(data, default_flow_style=False, sort_keys=True),
        encoding="utf-8",
    )

    assert _compute_manifest_contract_hash(baseline) == _compute_manifest_contract_hash(
        reformatted
    )


def test_manifest_hash_matches_dispatches_on_prefix(tmp_path: Path) -> None:
    baseline = _write_project(tmp_path)
    legacy_hash = compute_manifest_hash(baseline)
    contract_hash = _compute_manifest_contract_hash(baseline)

    assert _manifest_hash_matches(legacy_hash, baseline) is True
    assert _manifest_hash_matches(contract_hash, baseline) is True

    baseline.write_text(_BASELINE_MANIFEST + _OUTCOME_SECTION, encoding="utf-8")

    assert _manifest_hash_matches(legacy_hash, baseline) is False
    assert _manifest_hash_matches(contract_hash, baseline) is True
    assert _manifest_hash_matches("sha256-unknown:deadbeef", baseline) is False
    assert _manifest_hash_matches("not-a-hash", baseline) is False


def test_new_locks_store_contract_prefixed_hash(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)

    lock = create_plan_lock(manifest_path, tmp_path)

    assert lock.manifest_hash.startswith("sha256-contract:")
    assert lock.manifest_hash == _compute_manifest_contract_hash(manifest_path)
    assert all(h.startswith("sha256-pyast:") for h in lock.test_hashes.values())


def test_plan_status_reports_match_after_outcome_capture(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = _write_project(tmp_path)
    create_plan_lock(manifest_path, tmp_path).save(
        tmp_path / ".maid" / "plan-locks" / "demo-task.lock.json"
    )

    manifest_path.write_text(_BASELINE_MANIFEST + _OUTCOME_SECTION, encoding="utf-8")
    exit_code = cmd_plan_status(_status_args(manifest_path, tmp_path))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["manifest_match"] is True

    manifest_path.write_text(
        (_BASELINE_MANIFEST + _OUTCOME_SECTION).replace(
            "name: demo", "name: demo_tampered"
        ),
        encoding="utf-8",
    )
    exit_code = cmd_plan_status(_status_args(manifest_path, tmp_path))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["manifest_match"] is False


def test_contract_hash_raises_on_unparseable_manifest(tmp_path: Path) -> None:
    assert hasattr(
        plan_lock_mod, "compute_manifest_contract_hash"
    ), "compute_manifest_contract_hash must be public on plan_lock"
    bad = tmp_path / "broken.manifest.yaml"
    bad.write_text("schema: [\n  this is not valid yaml: {{\n", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        plan_lock_mod.compute_manifest_contract_hash(bad)
