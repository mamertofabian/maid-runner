"""Leftover command_jobs must not disable grouped derived coverage.

Contract: manifests/drafts/121-29-keep-grouped-coverage-under-command-jobs.manifest.yaml
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from maid_runner.core.manifest import load_manifest


def test_leftover_command_jobs_still_collect_grouped_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.verify import _collect_artifact_coverage_evidence
    from maid_runner.core import runtime_evidence

    _write_coverage_project(tmp_path)
    conftest = tmp_path / "conftest.py"
    conftest.write_text("# approved\n")
    _write_maidrc(tmp_path, conftest, command_jobs=2, approve=True)
    sentinel = object()
    observed: list[object] = []

    def fake_collect(manifests, root, pytest_workers=None):
        observed.append((tuple(manifests), root, pytest_workers))
        return SimpleNamespace(evidence=sentinel)

    monkeypatch.setattr(runtime_evidence, "collect_runtime_evidence", fake_collect)

    evidence = _collect_artifact_coverage_evidence(
        tmp_path, "manifests", test_jobs=2, pytest_workers=8
    )

    assert evidence is sentinel
    assert observed


def test_unapproved_conftest_still_skips_grouped_evidence_when_command_jobs_exceed_one(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.verify import _collect_artifact_coverage_evidence
    from maid_runner.core import runtime_evidence

    _write_coverage_project(tmp_path)
    (tmp_path / "conftest.py").write_text("# unapproved\n")
    _write_maidrc(tmp_path, None, command_jobs=2, approve=False)

    def fake_collect(*args, **kwargs):
        raise AssertionError("unapproved conftest must not collect grouped evidence")

    monkeypatch.setattr(runtime_evidence, "collect_runtime_evidence", fake_collect)

    evidence = _collect_artifact_coverage_evidence(
        tmp_path, "manifests", test_jobs=2, pytest_workers=8
    )

    assert evidence is None


def _write_maidrc(
    root: Path, conftest: Path | None, *, command_jobs: int, approve: bool
) -> None:
    body = (
        "test_execution:\n"
        f"  command_jobs: {command_jobs}\n"
        "  pytest_workers: 8\n"
        "  accepted_pytest_worker_counts: [8]\n"
        "  max_processes: 16\n"
        "artifact_coverage:\n"
        "  evidence_mode: derived\n"
    )
    if approve and conftest is not None:
        digest = hashlib.sha256(conftest.read_bytes()).hexdigest()
        relative = conftest.relative_to(root).as_posix()
        body += (
            "  fixture_lifecycle_approvals:\n"
            "    - context_id: fixture::dummy:session\n"
            f"      conftest_path: {relative}\n"
            f'      sha256: "{digest}"\n'
        )
    (root / ".maidrc.yaml").write_text(body)


def _write_coverage_project(root: Path):
    (root / "src").mkdir(parents=True)
    (root / "src/alpha.py").write_text("def alpha():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests/test_alpha.py").write_text("from src.alpha import alpha\n")
    (root / "manifests").mkdir()
    path = root / "manifests/alpha.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Grouped coverage under leftover command_jobs"
type: refactor
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/alpha.py
      artifacts:
        - kind: function
          name: alpha
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_alpha.py
"""
    )
    return (load_manifest(path),)
