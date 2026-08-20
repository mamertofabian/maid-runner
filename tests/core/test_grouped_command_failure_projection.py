"""Grouped pytest failures project onto the originating command only.

Contract: manifests/drafts/121-30-project-grouped-command-failures.manifest.yaml
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.manifest import load_manifest


def test_grouped_sibling_failure_does_not_fail_passing_command_evidence(
    tmp_path: Path,
) -> None:
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    manifests = _write_grouped_pass_and_fail(tmp_path)

    run = collect_runtime_evidence(manifests, tmp_path)
    by_path = {item.identity.manifest_path: item for item in run.evidence.commands}
    alpha = by_path[manifests[0].source_path]
    beta = by_path[manifests[1].source_path]

    assert alpha.result.returncode == 0
    assert beta.result.returncode != 0
    assert not any(
        "pytest exited with status" in diagnostic.message
        for diagnostic in alpha.completeness.diagnostics
    )


def test_grouped_physical_result_still_reports_union_exit_code(tmp_path: Path) -> None:
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    manifests = _write_grouped_pass_and_fail(tmp_path)

    run = collect_runtime_evidence(manifests, tmp_path)

    assert run.test_result.success is False
    assert run.test_result.results[0].exit_code != 0


def _write_grouped_pass_and_fail(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/target.py").write_text("def target() -> bool:\n    return True\n")
    (root / "tests/test_alpha.py").write_text(
        "from src.target import target\n\n"
        "def test_alpha():\n"
        "    assert target() is True\n"
    )
    (root / "tests/test_beta.py").write_text(
        "from src.target import target\n\n"
        "def test_beta():\n"
        "    assert target() is False\n"
    )
    return (
        load_manifest(_write_manifest(root, "alpha", "tests/test_alpha.py")),
        load_manifest(_write_manifest(root, "beta", "tests/test_beta.py")),
    )


def _write_manifest(root: Path, slug: str, selector: str) -> Path:
    manifests = root / "manifests"
    manifests.mkdir(exist_ok=True)
    path = manifests / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Exercise {slug}"
type: feature
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: bool
  read:
    - tests/test_{slug}.py
validate:
  - python -m pytest -q {selector}
"""
    )
    return path
