from __future__ import annotations

import json
from pathlib import Path

try:
    from maid_runner.core._coverage_cache import (
        load_cached_coverage_report,  # noqa: F401
        write_cached_coverage_report,  # noqa: F401
    )
except ModuleNotFoundError:
    pass

try:
    from maid_runner.core._coverage_history_evidence import (
        collect_coverage_history_evidence,  # noqa: F401
    )
except ModuleNotFoundError:
    pass

try:
    from maid_runner.core._deep_coverage import (  # noqa: F401
        DeepCoverageResult,
        collect_deep_coverage,
    )
except ModuleNotFoundError:
    pass


def _write_source_project(root: Path) -> None:
    source = root / "src" / "session.py"
    source.parent.mkdir()
    source.write_text("def session(flag=False):\n    return 1 if flag else 0\n")


def test_config_loads_coverage_recommendation_policy(tmp_path: Path) -> None:
    from maid_runner.core.config import (
        CoverageRecommendationConfig,
        CriticalPathRule,
        load_config,
    )

    (tmp_path / ".maidrc.yaml").write_text(
        "coverage_recommendation:\n"
        "  critical_paths:\n"
        '    - pattern: "src/auth/**"\n'
        "      minimum_priority: critical\n"
        "  entrypoints:\n"
        "    - src/main.py\n"
        "  cache: false\n"
        "  deep:\n"
        "    command: [python, -m, pytest, tests, -q]\n"
    )

    policy = load_config(tmp_path).coverage_recommendation

    assert isinstance(policy, CoverageRecommendationConfig)
    assert len(policy.critical_paths) == 1
    assert isinstance(policy.critical_paths[0], CriticalPathRule)
    assert policy.critical_paths[0].pattern == "src/auth/**"
    assert policy.critical_paths[0].minimum_priority == "critical"
    assert policy.entrypoints == ("src/main.py",)
    assert policy.cache_enabled is False
    assert policy.deep_command == ("python", "-m", "pytest", "tests", "-q")


def test_critical_path_floor_changes_priority_without_changing_score(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    baseline = recommend_coverage(tmp_path)
    (tmp_path / ".maidrc.yaml").write_text(
        "coverage_recommendation:\n"
        "  critical_paths:\n"
        '    - pattern: "src/**"\n'
        "      minimum_priority: critical\n"
    )

    floored = recommend_coverage(tmp_path)

    assert floored.candidates[0].score == baseline.candidates[0].score
    assert floored.candidates[0].priority.value == "critical"
    assert any(
        "critical path policy" in reason.lower()
        for reason in floored.candidates[0].reasons
    )


def test_static_cache_hits_and_invalidates_when_source_changes(tmp_path: Path) -> None:
    from maid_runner.core._coverage_cache import (
        load_cached_coverage_report,
        write_cached_coverage_report,
    )
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    assert load_cached_coverage_report(tmp_path, "absent") is None
    assert callable(write_cached_coverage_report)

    first = recommend_coverage(tmp_path)
    second = recommend_coverage(tmp_path)
    (tmp_path / "src" / "session.py").write_text(
        "def session(flag=False):\n"
        "    if flag:\n"
        "        return 1\n"
        "    return 0\n"
    )
    third = recommend_coverage(tmp_path)

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert third.cache_status == "miss"
    assert (tmp_path / ".maid" / "cache" / "coverage-risk-v1.json").is_file()


def test_outcome_and_incident_matches_are_zero_point_context(tmp_path: Path) -> None:
    from maid_runner.core._coverage_history_evidence import (
        collect_coverage_history_evidence,
    )
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    maid_dir = tmp_path / ".maid"
    incidents = maid_dir / "incidents"
    incidents.mkdir(parents=True)
    (maid_dir / "outcomes.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "manifest_slug": "prior-session-change",
                        "status": "completed",
                        "declared_paths": ["src/session.py"],
                    }
                ]
            }
        )
    )
    (incidents / "session.incident.yaml").write_text(
        "manifest: manifests/session.manifest.yaml\n"
        "packet:\n"
        "  files:\n"
        "    - src/session.py\n"
        "pattern_tags:\n"
        "  - scope-escape\n"
    )

    recommendation = recommend_coverage(tmp_path).candidates[0]
    context = next(
        signal
        for signal in recommendation.signals
        if signal.name == "historical_context"
    )

    assert context.contribution == 0
    assert any("prior-session-change" in item for item in context.evidence)
    assert any("session.incident.yaml" in item for item in context.evidence)
    assert collect_coverage_history_evidence(tmp_path, ("src/session.py",))[
        "src/session.py"
    ]


def test_deep_mode_requires_explicit_command(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)

    try:
        recommend_coverage(tmp_path, deep=True)
    except ValueError as exc:
        assert "deep.command" in str(exc)
    else:
        raise AssertionError("deep mode must fail without explicit configuration")


def test_deep_mode_uses_python_coverage_and_bypasses_cache(tmp_path: Path) -> None:
    from maid_runner.core._deep_coverage import (
        DeepCoverageResult,
        collect_deep_coverage,
    )
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_session.py").write_text(
        "from src.session import session\n\n"
        "def test_session():\n"
        "    assert session(True) == 1\n"
    )
    (tmp_path / ".maidrc.yaml").write_text(
        "coverage_recommendation:\n"
        "  deep:\n"
        "    command: [python, -m, pytest, tests, -q]\n"
    )

    report = recommend_coverage(tmp_path, deep=True)
    recommendation = next(
        item for item in report.candidates if item.path == "src/session.py"
    )
    test_gap = next(
        signal
        for signal in recommendation.signals
        if signal.name == "test_reference_gap"
    )

    assert report.cache_status == "bypassed-deep"
    assert DeepCoverageResult.__name__ == "DeepCoverageResult"
    assert callable(collect_deep_coverage)
    assert test_gap.raw_value == "coverage_percent=100.0"
    assert test_gap.contribution == 0


def test_static_cache_invalidates_when_entrypoint_metadata_changes(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    first = recommend_coverage(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\n'
        '[project.scripts]\nsample = "src.session:session"\n'
    )

    second = recommend_coverage(tmp_path)
    signal = next(
        item
        for item in second.candidates[0].signals
        if item.name == "entrypoint_reachability"
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "miss"
    assert signal.raw_value is True


def test_deep_mode_rejects_pytest_prefixed_executables(
    tmp_path: Path,
) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    (tmp_path / ".maidrc.yaml").write_text(
        "coverage_recommendation:\n" "  deep:\n" "    command: [pytest-evil]\n"
    )

    try:
        recommend_coverage(tmp_path, deep=True)
    except ValueError as exc:
        assert "must execute Python pytest" in str(exc)
    else:
        raise AssertionError("pytest-prefixed executables must be rejected")


def test_deep_mode_rejects_python_prefixed_executables(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    (tmp_path / ".maidrc.yaml").write_text(
        "coverage_recommendation:\n"
        "  deep:\n"
        "    command: [python-evil, -m, pytest]\n"
    )

    try:
        recommend_coverage(tmp_path, deep=True)
    except ValueError as exc:
        assert "must execute Python pytest" in str(exc)
    else:
        raise AssertionError("python-prefixed executables must be rejected")


def test_test_support_directory_is_evidence_not_a_candidate(tmp_path: Path) -> None:
    from maid_runner.core.coverage_recommendation import recommend_coverage

    _write_source_project(tmp_path)
    helpers = tmp_path / "tests" / "helpers.py"
    helpers.parent.mkdir()
    helpers.write_text("from src.session import session\n")

    report = recommend_coverage(tmp_path)

    assert {item.path for item in report.candidates} == {"src/session.py"}
    direct = next(
        signal
        for signal in report.candidates[0].signals
        if signal.name == "direct_dependents"
    )
    assert direct.raw_value == 0


def test_repository_ignores_generated_coverage_cache() -> None:
    repository_root = Path(__file__).resolve().parents[2]

    assert ".maid/cache/" in (repository_root / ".gitignore").read_text().splitlines()
