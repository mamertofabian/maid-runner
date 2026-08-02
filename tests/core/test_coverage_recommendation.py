from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

try:
    from maid_runner.core.coverage_recommendation import (
        CoverageConfidence,
        CoveragePriority,
        CoverageStatus,
    )
except ModuleNotFoundError:
    pass


def _write(root: Path, path: str, source: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)


def _manifest(root: Path, name: str, files: dict) -> None:
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    payload = {
        "schema": "2",
        "goal": name,
        "type": "feature",
        "files": files,
        "validate": ["pytest tests/ -q"],
        "created": "2026-07-31T00:00:00Z",
    }
    (manifest_dir / f"{name}.manifest.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False)
    )


def _signal(candidate, name: str):
    return next(signal for signal in candidate.signals if signal.name == name)


def test_recommendation_includes_incomplete_tracking_states_and_excludes_tracked(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import (
        CoverageRecommendationReport,
        recommend_coverage,
    )

    _write(tmp_path, "src/undeclared.py", "def undeclared():\n    return 1\n")
    _write(tmp_path, "src/read_only.py", "def read_only():\n    return 1\n")
    _write(tmp_path, "src/no_artifacts.py", "def no_artifacts():\n    return 1\n")
    _write(tmp_path, "src/tracked.py", "def tracked():\n    return 1\n")
    _write(tmp_path, "src/owner.py", "def owner():\n    return 1\n")
    _manifest(
        tmp_path,
        "read-only",
        {
            "edit": [
                {
                    "path": "src/owner.py",
                    "artifacts": [{"kind": "function", "name": "owner"}],
                }
            ],
            "read": ["src/read_only.py"],
        },
    )
    _manifest(
        tmp_path,
        "no-artifacts",
        {
            "delete": [
                {
                    "path": "src/no_artifacts.py",
                    "reason": "File is scheduled for removal but still exists.",
                }
            ]
        },
    )
    _manifest(
        tmp_path,
        "tracked",
        {
            "edit": [
                {
                    "path": "src/tracked.py",
                    "artifacts": [{"kind": "function", "name": "tracked"}],
                }
            ]
        },
    )

    report = recommend_coverage(tmp_path)

    assert isinstance(report, CoverageRecommendationReport)
    assert report.model == "risk-v1"
    assert report.cache_status == "miss"
    by_path = {candidate.path: candidate for candidate in report.candidates}
    assert set(by_path) == {
        "src/undeclared.py",
        "src/read_only.py",
        "src/no_artifacts.py",
    }
    assert by_path["src/undeclared.py"].coverage_status is CoverageStatus.UNDECLARED
    assert (
        by_path["src/no_artifacts.py"].coverage_status
        is CoverageStatus.WRITABLE_NO_ARTIFACTS
    )
    assert by_path["src/read_only.py"].coverage_status is CoverageStatus.READ_ONLY
    assert _signal(by_path["src/undeclared.py"], "coverage_gap").contribution == 30.0
    assert _signal(by_path["src/no_artifacts.py"], "coverage_gap").contribution == 22.0
    assert _signal(by_path["src/read_only.py"], "coverage_gap").contribution == 14.0


def test_dependency_evidence_separates_production_and_test_importers(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write(tmp_path, "src/target.py", "def target():\n    return 1\n")
    _write(
        tmp_path,
        "src/importer.py",
        "from src.target import target\n\ndef use():\n    return target()\n",
    )
    _write(
        tmp_path,
        "tests/test_target.py",
        "from src.target import target\n\ndef test_target():\n    assert target() == 1\n",
    )

    report = recommend_coverage(tmp_path)
    target = next(item for item in report.candidates if item.path == "src/target.py")

    assert _signal(target, "direct_dependents").raw_value == 1
    assert _signal(target, "test_reference_gap").raw_value is False


def test_parse_failure_is_low_confidence_and_not_zero_risk(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import (
        CoverageConfidence,
        recommend_coverage,
    )

    _write(tmp_path, "src/broken.py", "def broken(:\n")

    report = recommend_coverage(tmp_path)
    candidate = report.candidates[0]
    public_surface = _signal(candidate, "public_artifacts")
    complexity = _signal(candidate, "complexity")

    assert candidate.confidence is CoverageConfidence.LOW
    assert public_surface.normalized_value is None
    assert public_surface.contribution == 3.0
    assert complexity.contribution >= 7.5


def test_explain_tracked_file_reports_non_candidate_without_score(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import (
        CoverageExplanation,
        explain_coverage,
    )

    _write(tmp_path, "src/tracked.py", "def tracked():\n    return 1\n")
    _manifest(
        tmp_path,
        "tracked",
        {
            "edit": [
                {
                    "path": "src/tracked.py",
                    "artifacts": [{"kind": "function", "name": "tracked"}],
                }
            ]
        },
    )

    explanation = explain_coverage(tmp_path, "src/tracked.py")

    assert isinstance(explanation, CoverageExplanation)
    assert explanation.path == "src/tracked.py"
    assert explanation.eligible is False
    assert explanation.coverage_status is CoverageStatus.TRACKED
    assert explanation.exclusion_reason == "fully tracked"
    assert explanation.recommendation is None


def test_report_types_and_priority_bands_are_stable(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import (
        CoverageRecommendation,
        CoverageSignal,
        recommend_coverage,
    )

    _write(tmp_path, "src/app.py", "def app():\n    return 1\n")

    report = recommend_coverage(tmp_path)
    candidate = report.candidates[0]

    assert isinstance(candidate, CoverageRecommendation)
    assert isinstance(candidate.signals[0], CoverageSignal)
    assert candidate.signals[0].raw_value is not None
    assert isinstance(candidate.signals[0].evidence, tuple)
    assert isinstance(candidate.score, float)
    assert candidate.priority in {
        CoveragePriority.CRITICAL,
        CoveragePriority.HIGH,
        CoveragePriority.MEDIUM,
        CoveragePriority.LOW,
    }
    assert {status.value for status in CoverageStatus} == {
        "undeclared",
        "writable-no-artifacts",
        "read-only",
        "tracked",
    }
    assert {confidence.value for confidence in CoverageConfidence} == {
        "high",
        "medium",
        "low",
    }
    assert report.repository_head is None
    assert report.total_candidates == 1
    assert report.limit == 20
    assert isinstance(report.warnings, tuple)
    assert candidate.reasons
    assert candidate.recommended_action in {"baseline-now", "baseline-next"}


def test_repository_history_uses_one_git_log_process_for_all_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    for name in ("a", "b", "c"):
        _write(tmp_path, f"src/{name}.py", f"def {name}():\n    return 1\n")

    calls: list[tuple[str, ...]] = []
    real_run = subprocess.run

    def record_run(argv, *args, **kwargs):
        if list(argv[:2]) == ["git", "log"]:
            calls.append(tuple(argv))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", record_run)

    recommend_coverage(tmp_path)

    assert len(calls) == 1


def test_dependency_parse_failure_is_conservative_and_not_normalized(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write(tmp_path, "src/broken.py", "def broken(:\n")

    recommendation = recommend_coverage(tmp_path).candidates[0]
    signals = {signal.name: signal for signal in recommendation.signals}

    assert signals["direct_dependents"].confidence.value == "low"
    assert signals["direct_dependents"].normalized_value is None
    assert signals["direct_dependents"].contribution == 4.5
    assert signals["transitive_dependents"].normalized_value is None
    assert signals["entrypoint_reachability"].normalized_value is None


def test_simple_undeclared_file_has_pinned_score_and_priority(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write(tmp_path, "src/simple.py", "def simple():\n    return 1\n")
    _write(
        tmp_path,
        ".maidrc.yaml",
        "coverage_recommendation:\n  cache: false\n",
    )

    recommendation = recommend_coverage(tmp_path).candidates[0]

    assert recommendation.score == 57.9
    assert recommendation.priority.value == "medium"
    assert 0 <= recommendation.score <= 100


def test_external_imports_do_not_lower_dependency_confidence(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write(
        tmp_path,
        "src/simple.py",
        "import os\n\ndef simple():\n    return os.getcwd()\n",
    )

    recommendation = recommend_coverage(tmp_path).candidates[0]
    signals = {signal.name: signal for signal in recommendation.signals}

    assert signals["direct_dependents"].confidence.value == "high"
    assert signals["direct_dependents"].contribution == 0
    assert signals["transitive_dependents"].contribution == 0
    assert signals["entrypoint_reachability"].contribution == 0
