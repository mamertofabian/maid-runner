"""Task-scoped coverage and knockout use the changed-manifest closure.

Contract: manifests/drafts/121-24-task-scoped-deep-verification.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.artifact_coverage import ArtifactCoverageReport
from maid_runner.core.knockout import KnockoutReport
from maid_runner.core.manifest import load_manifest


def test_coverage_directory_run_limits_batch_to_selected_manifests(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.validate import _run_artifact_coverage_by_manifest

    manifests = _write_two_manifests(tmp_path)
    captured: list[list[str]] = []

    def fake_batch(selected, project_root, **kwargs):
        captured.append([item.source_path for item in selected])
        return {
            item.source_path: ArtifactCoverageReport(findings=(), errors=())
            for item in selected
        }

    monkeypatch.setattr(
        "maid_runner.core.artifact_coverage.run_artifact_coverage_batch",
        fake_batch,
    )

    reports = _run_artifact_coverage_by_manifest(
        "manifests",
        tmp_path,
        manifest_paths=(manifests[1].source_path,),
    )

    assert captured == [[manifests[1].source_path]]
    assert list(reports) == [manifests[0].source_path, manifests[1].source_path]
    assert reports[manifests[0].source_path].findings == ()
    assert reports[manifests[1].source_path].success is True


def test_knockout_stage_limits_batch_to_selected_manifests(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.verify import _knockout_stage

    manifests = _write_two_manifests(tmp_path)
    captured: list[list[str]] = []

    def fake_knockout(selected, project_root, **kwargs):
        captured.append([item.source_path for item in selected])
        return {
            item.source_path: KnockoutReport(results=(), errors=()) for item in selected
        }

    monkeypatch.setattr("maid_runner.core.knockout.run_knockout_batch", fake_knockout)

    stage = _knockout_stage(
        tmp_path,
        "manifests",
        limit=None,
        allow_dirty=False,
        manifest_paths=(manifests[0].source_path,),
    )

    assert captured == [[manifests[0].source_path]]
    assert stage.success is True


def test_unspecified_manifest_paths_keep_full_coverage_chain(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.validate import _run_artifact_coverage_by_manifest

    manifests = _write_two_manifests(tmp_path)
    captured: list[int] = []

    def fake_batch(selected, project_root, **kwargs):
        captured.append(len(list(selected)))
        return {
            item.source_path: ArtifactCoverageReport(findings=(), errors=())
            for item in selected
        }

    monkeypatch.setattr(
        "maid_runner.core.artifact_coverage.run_artifact_coverage_batch",
        fake_batch,
    )

    _run_artifact_coverage_by_manifest("manifests", tmp_path)

    assert captured == [2]
    assert {item.source_path for item in manifests}


def _write_two_manifests(root: Path):
    (root / "src").mkdir()
    (root / "src/alpha.py").write_text("def alpha():\n    return 1\n")
    (root / "src/beta.py").write_text("def beta():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests/test_alpha.py").write_text("from src.alpha import alpha\n")
    (root / "tests/test_beta.py").write_text("from src.beta import beta\n")
    (root / "manifests").mkdir()
    paths = []
    for name in ("alpha", "beta"):
        path = root / "manifests" / f"{name}.manifest.yaml"
        path.write_text(
            f"""schema: "2"
goal: "Task scope {name}"
type: refactor
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/{name}.py
      artifacts:
        - kind: function
          name: {name}
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_{name}.py
"""
        )
        paths.append(load_manifest(path))
    return tuple(paths)
