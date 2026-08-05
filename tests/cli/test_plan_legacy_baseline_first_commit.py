"""Behavioral contract for first-commit brownfield legacy baselines."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    capture_legacy_baseline_evidence,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _manifest_text(
    *,
    implementation_path: str = "src/demo.py",
    test_path: str = "tests/test_demo.py",
) -> str:
    return f"""schema: "2"
goal: "Adopt completed brownfield code"
type: fix
created: "2026-08-05T00:00:00Z"
files:
  edit:
    - path: {implementation_path}
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
  read:
    - {test_path}
validate:
  - python scripts/validate.py
"""


def _write_brownfield_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir(parents=True)
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "scripts" / "validate.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    (project_root / ".gitignore").write_text(".maid/\n", encoding="utf-8")
    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "maid-test@example.com")
    _git(project_root, "config", "user.name", "MAID Test")
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-qm", "completed brownfield implementation")

    manifest_path = project_root / "manifests" / "brownfield.manifest.yaml"
    manifest_path.write_text(_manifest_text(), encoding="utf-8")
    return manifest_path


def test_staged_first_commit_manifest_records_index_provenance_and_satisfies_strict_gate(
    tmp_path: Path,
) -> None:
    manifest_path = _write_brownfield_project(tmp_path)
    _git(tmp_path, "add", "manifests/brownfield.manifest.yaml")
    staged_bytes = manifest_path.read_bytes()

    evidence = capture_legacy_baseline_evidence(
        manifest_path,
        tmp_path,
        "Adopt implementation already committed before its MAID contract",
    )

    assert evidence.baseline_manifest_source == "index"
    assert (
        evidence.baseline_commit == _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    )
    assert evidence.baseline_manifest_hash == hashlib.sha256(staged_bytes).hexdigest()
    assert evidence.contract_delta.artifacts_added == ()
    assert evidence.contract_delta.files_added == ()
    assert evidence.commands[0].exit_code == 0
    assert evidence.to_payload()["baseline_manifest_source"] == "index"

    lock = replace(
        create_plan_lock(manifest_path, tmp_path),
        legacy_baseline=evidence.to_payload(),
    )
    lock_path = default_plan_lock_path(tmp_path, "brownfield")
    lock.save(lock_path)

    assert (
        enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=True,
            changed_paths={"manifests/brownfield.manifest.yaml"},
            plan_lock_scope="task",
        )
        == ()
    )


def test_first_commit_manifest_must_be_staged_and_match_the_worktree(
    tmp_path: Path,
) -> None:
    unstaged_root = tmp_path / "unstaged"
    unstaged_manifest = _write_brownfield_project(unstaged_root)

    with pytest.raises(ValueError, match="staged"):
        capture_legacy_baseline_evidence(
            unstaged_manifest, unstaged_root, "Unstaged manifests are not auditable"
        )

    mismatch_root = tmp_path / "mismatch"
    mismatch_manifest = _write_brownfield_project(mismatch_root)
    _git(mismatch_root, "add", "manifests/brownfield.manifest.yaml")
    mismatch_manifest.write_text(
        mismatch_manifest.read_text(encoding="utf-8") + "# unstaged change\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="match the staged index blob"):
        capture_legacy_baseline_evidence(
            mismatch_manifest,
            mismatch_root,
            "The audited manifest must match the worktree",
        )


def test_first_commit_manifest_rejects_declared_or_test_paths_absent_from_head(
    tmp_path: Path,
) -> None:
    cases = (
        ("implementation", "src/new_demo.py", "tests/test_demo.py"),
        ("test", "src/demo.py", "tests/test_new_demo.py"),
    )
    for name, implementation_path, test_path in cases:
        project_root = tmp_path / name
        manifest_path = _write_brownfield_project(project_root)
        absent_path = project_root / (
            implementation_path if name == "implementation" else test_path
        )
        absent_path.parent.mkdir(parents=True, exist_ok=True)
        if name == "implementation":
            absent_path.write_text(
                "def demo() -> int:\n    return 1\n", encoding="utf-8"
            )
        else:
            absent_path.write_text(
                "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
                "    assert demo() == 1\n",
                encoding="utf-8",
            )
        with (project_root / ".gitignore").open("a", encoding="utf-8") as ignore:
            ignore.write(f"/{absent_path.relative_to(project_root).as_posix()}\n")
        _git(project_root, "add", ".gitignore")
        _git(project_root, "commit", "-qm", "ignore uncommitted contract path")
        manifest_path.write_text(
            _manifest_text(
                implementation_path=implementation_path,
                test_path=test_path,
            ),
            encoding="utf-8",
        )
        _git(project_root, "add", "manifests/brownfield.manifest.yaml")

        with pytest.raises(ValueError, match="must already exist at HEAD"):
            capture_legacy_baseline_evidence(
                manifest_path,
                project_root,
                "Ignored files cannot be grandfathered by the index path",
            )


def test_historical_legacy_payload_without_source_remains_valid(
    tmp_path: Path,
) -> None:
    manifest_path = _write_brownfield_project(tmp_path)
    _git(tmp_path, "add", "manifests/brownfield.manifest.yaml")
    _git(tmp_path, "commit", "-qm", "tracked legacy manifest")
    evidence = capture_legacy_baseline_evidence(
        manifest_path, tmp_path, "Preserve historical evidence compatibility"
    ).to_payload()
    evidence.pop("baseline_manifest_source", None)
    lock = replace(
        create_plan_lock(manifest_path, tmp_path),
        legacy_baseline=evidence,
    )
    lock_path = default_plan_lock_path(tmp_path, "brownfield")
    lock.save(lock_path)

    persisted = json.loads(lock_path.read_text(encoding="utf-8"))
    assert "baseline_manifest_source" not in persisted["legacy_baseline"]
    assert (
        enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=True,
            changed_paths={"manifests/brownfield.manifest.yaml"},
            plan_lock_scope="task",
        )
        == ()
    )
