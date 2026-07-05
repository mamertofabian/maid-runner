from __future__ import annotations

import json
import subprocess

from maid_runner.cli.commands._format import (
    format_verify_result,
    format_verify_summary,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import (
    ErrorCode,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.sarif import build_sarif_report
from maid_runner.core.verify_summary import build_verify_summary
from maid_runner.core import worktree


def _commit_all(project_dir, message: str = "commit") -> str:
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            message,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_manifest(project_dir, body: str) -> None:
    manifest_dir = project_dir / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    (manifest_dir / "scope.manifest.yaml").write_text(body)


def _write_source(project_dir, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _chain(project_dir) -> ManifestChain:
    return ManifestChain(project_dir / "manifests", project_root=project_dir)


def _evaluate_changed_scope(*args, **kwargs):
    return worktree.evaluate_changed_scope(*args, **kwargs)


def _basic_manifest() -> str:
    return """schema: "2"
goal: "Scope app"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: app
validate:
  - python -m pytest tests/test_app.py -q
"""


def test_evaluate_changed_scope_skips_when_no_baseline_and_clean_tree(tmp_path):
    _write_source(tmp_path, "src/app.py", "def app():\n    return 'ok'\n")
    _write_manifest(tmp_path, _basic_manifest())
    _commit_all(tmp_path, "baseline")

    decision = _evaluate_changed_scope(
        tmp_path,
        _chain(tmp_path),
        since=None,
        base_ref=None,
        include_tests=False,
        allow_clean_tree_skip=True,
    )

    assert isinstance(decision, worktree.ChangedScopeDecision)
    assert decision.errors == ()
    assert decision.skip_reason is not None
    assert "no baseline" in decision.skip_reason
    assert "clean tree" in decision.skip_reason


def test_evaluate_changed_scope_keeps_e115_when_tree_dirty(tmp_path):
    _write_source(tmp_path, "src/app.py", "def app():\n    return 'ok'\n")
    _write_manifest(tmp_path, _basic_manifest())
    _commit_all(tmp_path, "baseline")
    _write_source(tmp_path, "src/app.py", "def app():\n    return 'changed'\n")

    decision = _evaluate_changed_scope(
        tmp_path,
        _chain(tmp_path),
        since=None,
        base_ref=None,
        include_tests=False,
        allow_clean_tree_skip=True,
    )

    assert [error.code for error in decision.errors] == [
        ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED
    ]
    assert decision.skip_reason is None


def test_evaluate_changed_scope_uses_baseline_when_given(tmp_path):
    _write_source(tmp_path, "src/app.py", "def app():\n    return 'ok'\n")
    baseline = _commit_all(tmp_path, "baseline")
    _write_manifest(
        tmp_path,
        """schema: "2"
goal: "Scope dependency"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: app
  read:
    - src/dep.py
validate:
  - python -m pytest tests/test_app.py -q
""",
    )
    _write_source(tmp_path, "src/dep.py", "def dep():\n    return 'changed'\n")

    decision = _evaluate_changed_scope(
        tmp_path,
        _chain(tmp_path),
        since=baseline,
        base_ref=None,
        include_tests=False,
        allow_clean_tree_skip=True,
    )

    assert decision.skip_reason is None
    assert any(
        error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
        and error.location
        and error.location.file == "src/dep.py"
        for error in decision.errors
    )


def test_evaluate_changed_scope_keeps_e115_when_skip_disallowed(tmp_path):
    _write_source(tmp_path, "src/app.py", "def app():\n    return 'ok'\n")
    _write_manifest(tmp_path, _basic_manifest())
    _commit_all(tmp_path, "baseline")

    decision = _evaluate_changed_scope(
        tmp_path,
        _chain(tmp_path),
        since=None,
        base_ref=None,
        include_tests=False,
        allow_clean_tree_skip=False,
    )

    assert [error.code for error in decision.errors] == [
        ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED
    ]
    assert decision.skip_reason is None


def test_stage_skip_reason_partitions_summary_buckets():
    result = VerificationResult(
        stages=(
            VerificationStageResult(name="schema", success=True),
            VerificationStageResult(
                name="changed_scope",
                success=True,
                skip_reason="no baseline; clean tree",
            ),
            VerificationStageResult(name="tests", success=True),
        )
    )

    summary = build_verify_summary(result)

    assert summary.skipped_stages == ("changed_scope",)
    assert summary.passed_stages == ("schema", "tests")


def test_formatters_render_skipped_stage_distinctly():
    result = VerificationResult(
        stages=(
            VerificationStageResult(name="schema", success=True),
            VerificationStageResult(
                name="changed_scope",
                success=True,
                skip_reason="no baseline; clean tree",
            ),
        )
    )

    text = format_verify_result(result)
    default_json = json.loads(format_verify_result(result, json_mode=True))
    summary = format_verify_summary(result)
    summary_json = json.loads(format_verify_summary(result, json_mode=True))
    sarif = build_sarif_report(result)

    assert "SKIPPED changed_scope" in text
    assert "PASS changed_scope" not in text
    assert default_json["stages"][1]["skip_reason"] == "no baseline; clean tree"
    assert "SKIPPED (1): changed_scope (no baseline; clean tree)" in summary
    assert summary_json["skipped_stages"] == ["changed_scope"]
    assert summary_json["passed_stages"] == ["schema"]
    assert sarif["runs"][0]["properties"]["skippedStages"] == [
        {
            "name": "changed_scope",
            "reason": "no baseline; clean tree",
        }
    ]
